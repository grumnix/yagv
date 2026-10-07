#!/usr/bin/env python

YAGV_VERSION = "0.5.8"        # -- check Makefile and setup.py too

import pyglet
import math
import numpy as np

from pyglet import clock
from pyglet.gl import *
from pyglet.window import key
from pyglet.window import mouse

from .gcodeParser import *
import os.path
import re
import time

colorMap = {
	# Misc:
	"background": [ 1,1,1, 1. ],
	"grid": [ .2,.2,.2, 1. ],
	"text": [ 0,0,0, 1. ],

   # Gcode:
	"extrude": [ 0.,.8,0. ],
	"extrude_active": [ .8,0.,0. ],
	"extrude_wall": [ .2,.9,0. ],
	"extrude_wall_active": [ .8,.5,0. ],
	"extrude_support": [ .8,.8,0. ],
	"extrude_support_active": [ 1,.9,0. ],
	"retract": [ .8,.8,0. ],
	"unretract": [ .8,0.,.8 ],
	"motion": [ 0.,0.,1. ]
}

def resource_filename(package, name):
	return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)

VERTEX_SHADER = """#version 330 core
in vec3 position;
in vec4 colors;
out vec4 vertex_colors;
uniform mat4 mvp;

void main()
{
	gl_Position = mvp * vec4(position, 1.0);
	vertex_colors = colors;
}
"""

FRAGMENT_SHADER = """#version 330 core
in vec4 vertex_colors;
out vec4 final_color;

void main()
{
	if (vertex_colors.a == 0.0)
		discard;
	final_color = vertex_colors;
}
"""

# -- matrix helpers (row-major, column vectors, same conventions as the old fixed-function GL calls)
def mat_perspective(fovy, aspect, near, far):
	f = 1.0 / math.tan(math.radians(fovy) / 2.0)
	return np.array([
		[f/aspect, 0, 0, 0],
		[0, f, 0, 0],
		[0, 0, (far+near)/(near-far), 2*far*near/(near-far)],
		[0, 0, -1, 0]], dtype=np.float64)

def mat_look_at(eye, center, up):
	eye, center, up = (np.array(v, dtype=np.float64) for v in (eye, center, up))
	f = center - eye
	f /= np.linalg.norm(f)
	s = np.cross(f, up)
	s /= np.linalg.norm(s)
	u = np.cross(s, f)
	m = np.identity(4)
	m[0,:3], m[1,:3], m[2,:3] = s, u, -f
	m[:3,3] = -m[:3,:3] @ eye
	return m

def mat_rotate(angle, x, y, z):
	a = math.radians(angle)
	c, s = math.cos(a), math.sin(a)
	n = math.sqrt(x*x + y*y + z*z)
	x, y, z = x/n, y/n, z/n
	m = np.identity(4)
	m[:3,:3] = [
		[x*x*(1-c)+c,   x*y*(1-c)-z*s, x*z*(1-c)+y*s],
		[y*x*(1-c)+z*s, y*y*(1-c)+c,   y*z*(1-c)-x*s],
		[z*x*(1-c)-y*s, z*y*(1-c)+x*s, z*z*(1-c)+c]]
	return m

def mat_translate(x, y, z):
	m = np.identity(4)
	m[:3,3] = [x, y, z]
	return m

def mat_scale(x, y, z):
	return np.diag([x, y, z, 1.0])

def preg_match(rex,s,m,opts={}):
	_m = re.search(rex,s)
	m.clear()
	if _m:
		m.append(s)
		m.extend(_m.groups())
		return True
	return False
                              
class App:
	def __init__(self):
		self.RX = 0.0
		self.RZ = 0.0
		self.PX = 0.0
		self.PY = 0.0
		self.zoom = 1.0
		self.centerOnBed = False
		self.showGrid = True
		self.hiddenColors = set()
		self.conf = { }
		self.conf['bed_size'] = [ 200, 200 ]
	
	def main(self):
		
		#### MAIN CODE ####
		import sys

		path = ''

		i = 1
		while(i<len(sys.argv)):
			m = [ ]
			if preg_match(r'^--([\w\-]+)=(.*)$',sys.argv[i],m):
				m[1] = m[1].replace('-','_')
				self.conf[m[1]] = m[2]
			elif preg_match(r'^--([\w\-]+)$',sys.argv[i],m):
				m[1] = m[1].replace('-','_')
				self.conf[m[1]] = 1
			else:
		 		path = sys.argv[i]
			i += 1

		if 'help' in self.conf and self.conf['help']:
			print("""USAGE yagv %s: [<opts>] file.gcode
   options:
      --help               display this message
      --dark               enable dark mode
      --bed-size=<w>x<h>   set bed size (e.g. 200x240)
""" % YAGV_VERSION)
			sys.exit(0)
		if 'dark' in self.conf and self.conf['dark']:
			colorMap['background'] = [ 0,0,0, 1 ]
			colorMap['grid'] = [ 1,1,1, 0.1 ]
			colorMap['text'] = [ 1,1,1, 0.7 ]

		if type(self.conf['bed_size'])==str:
			self.conf['bed_size'] = list(map(lambda x: int(x),self.conf['bed_size'].split('x')))

		if len(path)==0:
			script_path = os.path.realpath(__file__)
			script_dir = os.path.dirname(script_path)
			path = resource_filename("yagv", "data/hana_swimsuit_fv_solid_v1.gcode")

		print("Yet Another GCode Viewer v%s"%YAGV_VERSION)

		self.path = "loading ..."

		# -- create window soon, before loading ...
		self.window = MyWindow(self, caption="Yet Another GCode Viewer v%s: %s" % (YAGV_VERSION,os.path.basename(path)), resizable=True, width=1024, height=768, file_drops=True)
		pyglet.gl.glClearColor(colorMap['background'][0],colorMap['background'][1],colorMap['background'][2],1)

		# debug: log all events
		# self.window.push_handlers(pyglet.window.event.WindowEventLogger())

		if not self.load(path):
			sys.exit(1)

		# default to the middle layer
		self.layerIdx = len(self.model.layers)//2
		self.window.hud()

		img = pyglet.image.load(resource_filename("yagv", "data/icon.png"))
		self.window.set_icon(img)

		pyglet.app.run()

	def reload(self):
		if self.load(self.path):
			self.layerIdx = min(self.layerIdx, self.model.topLayer)
			self.window.hud()

	def open_file(self, path):
		"""Load a new file (e.g. dropped onto the window), keeping the current one on failure"""
		if self.load(path):
			self.layerIdx = len(self.model.layers)//2
			self.reset_view()
			self.window.hud()
			self.window.set_caption("Yet Another GCode Viewer v%s: %s" % (YAGV_VERSION, os.path.basename(path)))

	def load(self, path):
		"""Parse and render a gcode file, returns False (and keeps the old model) on failure"""

		print("loading file %s ..." % repr(path))
		t1 = time.time()
		
		print("Parsing '%s'..." % path)

		try:
			model = GcodeParser().parseFile(path)
		except (OSError, UnicodeDecodeError) as e:
			print("[ERROR] Can't read %s: %s" % (repr(path), e))
			return False
		if len(model.layers) == 0:
			print("[ERROR] No printable layers found in %s" % repr(path))
			return False

		self.path = path
		self.model = model

		print("Done! %s" % self.model)
		
		# render the model
		print("rendering vertices...")
		self.renderVertices()
		print("rendering indexed colors...")
		self.renderIndexedColors()
		print("rendering true colors...")
		self.renderColors()
		print("generating graphics...")
		self.generateGraphics()
		self.window.makeDecor()
		print("Done")
		
		t2 = time.time()
		print("loaded file in %0.3f ms" % ((t2-t1)*1000.0 ))
		return True
	
	def renderVertices(self):
		t1 = time.time()
		
		self.vertices = []

		for layer in self.model.layers:
			
			layer_vertices = []
			
			x = layer.start["X"]
			y = layer.start["Y"]
			z = layer.start["Z"]
			for seg in layer.segments:
				layer_vertices.append(x)
				layer_vertices.append(y)
				layer_vertices.append(z)
				x = seg.coords["X"]
				y = seg.coords["Y"]
				z = seg.coords["Z"]
				layer_vertices.append(x)
				layer_vertices.append(y)
				layer_vertices.append(z)

			self.vertices.append(layer_vertices)
			#layer.end['X'] = layer_vertices[:3]
			#layer.end['Y'] = layer_vertices[:2]
			#layer.end['Z'] = layer_vertices[:1]
			
		t2 = time.time()
		print("end renderVertices in %0.3f ms" % ((t2-t1)*1000.0, ))
	
	def renderIndexedColors(self):
		t1 = time.time()
		# pre-render segments to colors in the index
		styleToColoridx = {
			"extrude" : 0,
			"fly" : 1,
			"retract" : 2,
			"restore" : 3,
	  		"extrude.wall": 4,
			"extrude.support": 5
			}
		
		# all the styles for all layers
		self.vertex_indexed_colors = []
		
		# for all layers
		for layer in self.model.layers:
			
			# index for this layer
			layer_vertex_indexed_colors = []
			for seg in layer.segments:
				# get color index for this segment
				if seg.style == 'extrude' and (seg.type == 'G1:wall' or seg.type == 'G1:shell' or seg.type == 'G1:perimeter' or seg.type.find('shell') or seg.type.find('shell')):
					styleCol = styleToColoridx['extrude.wall']
				elif seg.style == 'extrude' and seg.type == 'G1:support':
					styleCol = styleToColoridx['extrude.support']
				else:
					styleCol = styleToColoridx[seg.style]
				# append color twice (once per end)
				layer_vertex_indexed_colors.extend((styleCol, styleCol))
			
			# append layer to all layers
			self.vertex_indexed_colors.append(layer_vertex_indexed_colors)
		t2 = time.time()
		print("end renderIndexedColors in %0.3f ms" % ((t2-t1)*1000.0, ))
	
	def renderColors(self):
		t1 = time.time()
		
		self.vertex_colors = [[],[],[]]
		
		# render color index to real colors
		cm = [ 
			# 0: old layer
			[ colorMap['extrude'].copy(),        colorMap['motion'].copy(), colorMap['retract'].copy(), colorMap['unretract'].copy(), colorMap['extrude_wall'].copy(), colorMap['extrude_support'].copy() ],
			# 1: current layer
			[ colorMap['extrude_active'].copy(), colorMap['motion'].copy(), colorMap['retract'].copy(), colorMap['unretract'].copy(), colorMap['extrude_wall_active'].copy(), colorMap['extrude_support_active'].copy() ],
			# 2: limbo layer
			[ colorMap['extrude'].copy(),        colorMap['motion'].copy(), colorMap['retract'].copy(), colorMap['unretract'].copy(), colorMap['extrude_wall'].copy(), colorMap['extrude_support'].copy() ]
		]
		for i in range(6):         # -- add per type the alpha
			if i in self.hiddenColors:
				for t in range(3):
					cm[t][i].append(0.)
				continue
			cm[0][i].append(.2 if i==1 or i==5 else .7)    # -- old
			cm[1][i].append(.2 if i==1 else 1.)    # -- current
			cm[2][i].append(.1)    # -- limbo
		
		# for all 3 types
		for display_type in range(3):
			
			#type_color_map = cm[display_type]

			# -- cumbersome float -> int color
			type_color_map = []
			n = 0
			for c in cm[display_type]:
				type_color_map.append([])
				for i in range(4):
					type_color_map[n].append(int(c[i]*255))
				n += 1

			# for all preindexed layer colors
			for indexes in self.vertex_indexed_colors:
				
				# render color indexes to colors
				colors = list(map(lambda e: type_color_map[e], indexes))
				# flatten color values
				fcolors = []
				list(map(fcolors.extend, colors))
				
				# push colors to vertex list
				self.vertex_colors[display_type].append(fcolors)
				
		t2 = time.time()
		print("end renderColors in %0.3f ms" % ((t2-t1)*1000.0, ))
	
	def generateGraphics(self):
		t1 = time.time()
		
		for graphics in (getattr(self, 'graphics_old', []), getattr(self, 'graphics_current', []), getattr(self, 'graphics_limbo', [])):
			for vlist in graphics:
				vlist.delete()
		self.graphics_old = []
		self.graphics_current = []
		self.graphics_limbo = []
		
		program = self.window.program
		for layer_idx in range(len(self.vertices)):
			nb_layer_vertices = len(self.vertices[layer_idx])//3
			for graphics, colors in ((self.graphics_old, self.vertex_colors[0]),
			                         (self.graphics_current, self.vertex_colors[1]),
			                         (self.graphics_limbo, self.vertex_colors[2])):
				graphics.append(program.vertex_list(nb_layer_vertices, GL_LINES,
					position=('f', self.vertices[layer_idx]),
					colors=('Bn', colors[layer_idx])))
		
		t2 = time.time()
		print("end generateGraphics in %0.3f ms" % ((t2-t1)*1000.0, ))
		
	# -- rotate		
	def rotate_drag_start(self, x, y, button, modifiers):
		self.rotateDragStartRX = self.RX
		self.rotateDragStartRZ = self.RZ
		self.rotateDragStartX = x
		self.rotateDragStartY = y

	def rotate_drag_do(self, x, y, dx, dy, buttons, modifiers):
		# deltas
		deltaX = x - self.rotateDragStartX
		deltaY = y - self.rotateDragStartY
		# rotate!
		self.RZ = self.rotateDragStartRZ + deltaX/5.0 # mouse X bound to model Z
		self.RX = self.rotateDragStartRX + deltaY/5.0 # mouse Y bound to model X

	def rotate_drag_end(self, x, y, button, modifiers):
		self.rotateDragStartRX = None
		self.rotateDragStartRZ = None
		self.rotateDragStartX = None
		self.rotateDragStartY = None

	def layer_drag_start(self, x, y, button, modifiers):
		self.layerDragStartLayer = self.layerIdx
		self.layerDragStartX = x
		self.layerDragStartY = y

	def layer_drag_do(self, x, y, dx, dy, buttons, modifiers):
		# sum x & y
		delta = x - self.layerDragStartX + y - self.layerDragStartY
		# new theoretical layer
		self.layerIdx = int(self.layerDragStartLayer + delta//5)
		# clamp layer to 0-max
		self.layerIdx = max(min(self.layerIdx, self.model.topLayer), 0)
		self.layer_update()
		
	#	# clamp layer to 0-max, with origin slip
	#	if (self.layerIdx < 0):
	#		self.layerIdx = 0
	#		self.layerDragStartLayer = 0
	#		self.layerDragStartX = x
	#		self.layerDragStartY = y
	#	if (self.layerIdx > len(self.model.layers)-1):
	#		self.layerIdx = len(self.model.layers)-1
	#		self.layerDragStartLayer = len(self.model.layers)-1
	#		self.layerDragStartX = x
	#		self.layerDragStartY = y

	# -- layer select		
	def layer_update(self):
		#self.window.layerLabel.text = "layer %d (z=%.2f)" % (self.layerIdx,self.model.layers[self.layerIdx].start['Z'])
		if self.model.layers[self.layerIdx].bbox.zmin != self.model.layers[self.layerIdx].bbox.zmax:
			self.window.layerLabel.text = "layer %d (z=%.2f..%.2f)" % (self.layerIdx,self.model.layers[self.layerIdx].bbox.zmin,self.model.layers[self.layerIdx].bbox.zmax)
		else:
			self.window.layerLabel.text = "layer %d (z=%.2f)" % (self.layerIdx,self.model.layers[self.layerIdx].start['Z'])
		#print(self.model.layers[self.layerIdx].bbox.zmin)

	def layer_up(self):
		self.layerIdx = max(min(self.layerIdx+1, self.model.topLayer), 0)
		self.layer_update()

	def layer_down(self):
		self.layerIdx = max(min(self.layerIdx-1, self.model.topLayer), 0)
		self.layer_update()

	def layer_bottom(self):
		self.layerIdx = min(1, self.model.topLayer)
		self.layer_update()

	def layer_top(self):
		self.layerIdx = self.model.topLayer
		self.layer_update()

	def layer_step(self, n):
		self.layerIdx = max(min(self.layerIdx+n, self.model.topLayer), 0)
		self.layer_update()

	def toggle_color(self, *indexes):
		"""Show/hide segment kinds by color index (1: travel, 2+3: retract/restore)"""
		if indexes[0] in self.hiddenColors:
			self.hiddenColors.difference_update(indexes)
		else:
			self.hiddenColors.update(indexes)
		self.renderColors()
		for graphics, colors in ((self.graphics_old, self.vertex_colors[0]),
		                         (self.graphics_current, self.vertex_colors[1]),
		                         (self.graphics_limbo, self.vertex_colors[2])):
			for vlist, c in zip(graphics, colors):
				vlist.colors[:] = c

	def toggle_grid(self):
		self.showGrid = not self.showGrid

	def reset_view(self):
		self.RX = 0.0
		self.RZ = 0.0
		self.PX = 0.0
		self.PY = 0.0
		self.zoom = 1.0

	def toggle_center_on_bed(self):
		self.centerOnBed = not self.centerOnBed
		self.reset_view()

	def layer_drag_end(self, x, y, button, modifiers):
		self.layerDragStartLayer = None
		self.layerDragStartX = None
		self.layerDragStartY = None

	# -- panning
	def panning_start(self, x, y, button, modifiers):
		self.panningStartPX = self.PX
		self.panningStartPY = self.PY
		self.panningStartX = x
		self.panningStartY = y

	def panning_do(self, x, y, dx, dy, buttons, modifiers):
		# deltas
		#deltaX = x - self.panningStartX
		#deltaY = y - self.panningStartY
		# -- panning done with proper rotation
		deltaX = math.cos(-self.RZ/180*math.pi) * (x - self.panningStartX) + math.sin(self.RZ/180*math.pi) * (y - self.panningStartY)
		deltaY = math.sin(-self.RZ/180*math.pi) * (x - self.panningStartX) + math.cos(self.RZ/180*math.pi) * (y - self.panningStartY)
		# pan!
		f = 5
		self.PX = self.panningStartPX + deltaX/f # mouse X bound to model X
		self.PY = self.panningStartPY + deltaY/f # mouse Y bound to model Y

	def panning_end(self, x, y, button, modifiers):
		self.panningStartX = None
		self.panningStartY = None


class MyWindow(pyglet.window.Window):

	# constructor
	def __init__(self, app, **kwargs):
		pyglet.window.Window.__init__(self, **kwargs)
		self.app = app
		self.program = pyglet.graphics.shader.ShaderProgram(
			pyglet.graphics.shader.Shader(VERTEX_SHADER, 'vertex'),
			pyglet.graphics.shader.Shader(FRAGMENT_SHADER, 'fragment'))
		self.decor = []
		#self.hud()
	
	# hud info
	def hud(self):
		
		# HUD labels
		self.blLabels = []
		self.brLabels = []
		self.tlLabels = []
		self.trLabels = []

		c_texti = list(map(lambda x: int(x*255), colorMap['text']))
		#self.brLabels.append(pyglet.text.Label("yagv "+YAGV_VERSION,font_size=10,color=c_texti,anchor_x='right', anchor_y='bottom'))
      
		# help
		self.helpText = [
						"Left-mouse: rotate | Middle: change layer, Scroll: zoom | Right: panning",
						"Up/Down/PgUp/PgDn/Home/End: layer | Space: reset view | B: center on bed/model | T/R/G: toggle travel/retracts/grid | Ctrl-R: reload"]
		for txt in self.helpText:
			self.blLabels.append(
				pyglet.text.Label(	txt,
									font_size=10,color=c_texti) )

		# statistics
		## model stats
		self.statsLabel = pyglet.text.Label(	"",
										font_size=10,color=c_texti,
										anchor_y='top')
		filename = os.path.basename(self.app.path)
		self.statsLabel.text = "%s: %d layers (%d segments), %.1fm filament" % (filename, len(self.app.model.layers), len(self.app.model.segments), self.app.model.extrudate/1000.0)
		
		## fps counter
		self.fpsLabel = pyglet.text.Label(	"",
										font_size=10,color=c_texti,
										anchor_y='top')
		self.tlLabels.append(self.statsLabel)
		#self.tlLabels.append(self.fpsLabel)

		# status
		## current Layer
		self.layerLabel = pyglet.text.Label(	"layer %d (z=%.2f)" % (
			self.app.layerIdx,
			self.app.model.layers[self.app.layerIdx].start['Z'],
			#self.app.model.layers[self.app.layerIdx].end['Z']
			#self.app.model.layers[self.app.layerIdx].bbox.zmin,
			#self.app.model.layers[self.app.layerIdx].bbox.zmax
			), font_size=10,color=c_texti,anchor_x='right', anchor_y='top')
		self.trLabels.append(self.layerLabel)

		# layout the labels in the window's corners
		self.placeLabels(self.width, self.height)
	
	
	# events
	def on_resize(self, width, height):
		# the default handler sets viewport and the projection used by the labels
		super().on_resize(width, height)
		self.placeLabels(width, height)

	def on_file_drop(self, x, y, paths):
		# return right away so the drag source isn't kept waiting while we parse
		if paths:
			pyglet.clock.schedule_once(lambda dt: self.app.open_file(paths[0]), 0)

	def on_mouse_press(self, x, y, button, modifiers):
		#print("on_mouse_press(x=%d, y=%d, button=%s, modifiers=%s)"%(x, y, button, modifiers))
		if button & mouse.LEFT:
			self.app.rotate_drag_start(x, y, button, modifiers)
			
		if button & mouse.MIDDLE:
			self.app.layer_drag_start(x, y, button, modifiers)

		if button & mouse.RIGHT:
			self.app.panning_start(x, y, button, modifiers)


	def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
		#print("on_mouse_drag(x=%d, y=%d, dx=%d, dy=%d, buttons=%s, modifiers=%s)"%(x, y, dx, dy, buttons, modifiers))
		if buttons & mouse.LEFT:
			self.app.rotate_drag_do(x, y, dx, dy, buttons, modifiers)
			
		if buttons & mouse.MIDDLE:
			self.app.layer_drag_do(x, y, dx, dy, buttons, modifiers)

		if buttons & mouse.RIGHT:
			self.app.panning_do(x, y, dx, dy, buttons, modifiers)


	def on_mouse_release(self, x, y, button, modifiers):
		#print("on_mouse_release(x=%d, y=%d, button=%s, modifiers=%s)"%(x, y, button, modifiers))
		if button & mouse.LEFT:
			self.app.rotate_drag_end(x, y, button, modifiers)
			
		if button & mouse.MIDDLE:
			self.app.layer_drag_end(x, y, button, modifiers)

		if button & mouse.RIGHT:
			self.app.panning_end(x, y, button, modifiers)

	def on_key_release(self, symbol, modifiers):
		#print("pressed key: %s, mod: %s"%(pyglet.window.key.R, pyglet.window.key.MOD_CTRL))

		if symbol==pyglet.window.key.R and modifiers & pyglet.window.key.MOD_CTRL:
			self.app.reload()
		elif symbol==pyglet.window.key.UP:
			self.app.layer_up()
		elif symbol==pyglet.window.key.DOWN:
			self.app.layer_down()
		elif symbol==pyglet.window.key.HOME:
			self.app.layer_bottom()
		elif symbol==pyglet.window.key.END:
			self.app.layer_top()
		elif symbol==pyglet.window.key.PAGEUP:
			self.app.layer_step(10)
		elif symbol==pyglet.window.key.PAGEDOWN:
			self.app.layer_step(-10)
		elif symbol==pyglet.window.key.SPACE:
			self.app.reset_view()
		elif symbol==pyglet.window.key.T:
			self.app.toggle_color(1)
		elif symbol==pyglet.window.key.R:
			self.app.toggle_color(2, 3)
		elif symbol==pyglet.window.key.G:
			self.app.toggle_grid()
		elif symbol==pyglet.window.key.B:
			self.app.toggle_center_on_bed()
		else:
			print("pressed key: %s, mod: %s"%(symbol, modifiers))
		
	def placeLabels(self, width, height):
		x = 5
		y = 5
		for label in self.blLabels:
			label.x = x
			label.y = y
			y += 20
			
		x = width - 5
		y = 5
		for label in self.brLabels:
			label.x = x
			label.y = y
			y += 20
			
		x = 5
		y = height - 5
		for label in self.tlLabels:
			label.x = x
			label.y = y
			y -= 20
			
		x = width - 5
		y = height - 5
		for label in self.trLabels:
			label.x = x
			label.y = y
			y -= 20


	def on_mouse_scroll(self, x, y, dx, dy):
		# zoom on mouse scroll
		delta = dx + dy
		if delta == 0:
			return
		z = 1.2 if delta>0 else 1/1.2
		self.app.zoom = max(1.0, self.app.zoom * z)
		#print('mouse scroll:', `x, y, dx, dy`, `z, self.app.zoom`)

	def makeDecor(self):
		"""Build the axes and bed grid line lists, call whenever the model changes."""
		model = self.app.model
		bed = self.app.conf['bed_size']
		verts = []
		colors = []

		def line(p1, p2, c):
			verts.extend(p1)
			verts.extend(p2)
			colors.extend(list(map(lambda x: int(x*255), c))*2)

		# axes
		line([0,0,0], [1,0,0], [1,0,0,1]); line([1,0,0], [1,0.1,0], [1,0,0,1]); line([1,0,0], [model.bbox.xmax,0,0], [1,0,0,1])
		line([0,0,0], [0,1,0], [0,1,0,1]); line([0,1,0], [0,1,0.1], [0,1,0,1]); line([0,1,0], [0,model.bbox.ymax,0], [0,1,0,1])
		line([0,0,0], [0,0,1], [0,0,1,1]); line([0,0,1], [0.1,0,1], [0,0,1,1]); line([0,0,1], [0,0,model.bbox.zmax], [0,0,1,1])

		# bed grid
		g = colorMap['grid']
		for y in range(0, bed[1]+1):
			line([0,y,0], [bed[0],y,0], [g[0],g[1],g[2],0.3 if y%10 == 0 else 0.1])
		for x in range(0, bed[0]+1):
			line([x,0,0], [x,bed[1],0], [g[0],g[1],g[2],0.3 if x%10 == 0 else 0.1])

		for vlist in self.decor:
			vlist.delete()
		self.decor = [ self.program.vertex_list(len(verts)//3, GL_LINES,
			position=('f', verts), colors=('Bn', colors)) ]

	def on_draw(self):
		# Clear buffers
		glDepthMask(1)
		glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
		glEnable(GL_DEPTH_TEST)

		# enable alpha blending
		glEnable(GL_BLEND)
		glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

		# projection and camera
		m = mat_perspective(65, self.width / float(max(self.height, 1)), 0.1, 1000)
		m = m @ mat_look_at((0,1.5,2), (0,0,0), (0,1,0))

		# rotate axes to match reprap style
		m = m @ mat_rotate(-90, 1,0,0)

		# user rotate model
		m = m @ mat_rotate(-self.app.RX, 1,0,0)
		m = m @ mat_rotate(self.app.RZ, 0,0,1)

		# Todo check this
		m = m @ mat_translate(0,0,-0.5)

		# fit & user zoom model
		bed = self.app.conf['bed_size']
		if self.app.centerOnBed:
			max_width = max(bed[0], bed[1], self.app.model.bbox.zmax)
			center = (bed[0]/2.0, bed[1]/2.0, self.app.model.bbox.cz())
		else:
			max_width = max(
				self.app.model.bbox.dx(),
				self.app.model.bbox.dy(),
				self.app.model.bbox.dz()
			)
			center = (self.app.model.bbox.cx(), self.app.model.bbox.cy(), self.app.model.bbox.cz())
		scale = self.app.zoom / max_width
		m = m @ mat_scale(scale, scale, scale)

		# user pan model
		m = m @ mat_translate(self.app.PX, self.app.PY, 0)

		m = m @ mat_translate(-center[0], -center[1], -center[2])

		# GL expects column-major
		self.program.use()
		self.program['mvp'] = tuple(m.T.flatten())

		# draw axes and bed grid
		if self.app.showGrid:
			for vlist in self.decor:
				vlist.draw(GL_LINES)

		# -- draw the model layers
		#    lower layers
		glLineWidth(1)
		for graphic in self.app.graphics_old[0:self.app.layerIdx]:
			graphic.draw(GL_LINES)
		
		#    highlighted layer
		glLineWidth(2)
		graphic = self.app.graphics_current[self.app.layerIdx]
		graphic.draw(GL_LINES)
		
		#    limbo layers
		glLineWidth(1)
		for graphic in self.app.graphics_limbo[self.app.layerIdx+1:]:
			graphic.draw(GL_LINES)
		
		self.program.stop()

		# disable depth for HUD
		glDisable(GL_DEPTH_TEST)
		glDepthMask(0)
		
		
		for label in self.blLabels:
			label.draw()
		for label in self.brLabels:
			label.draw()
		for label in self.tlLabels:
			label.draw()
		for label in self.trLabels:
			label.draw()
		


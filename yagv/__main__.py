import pyglet


def work_around_pyglet_xrandr_crash():
    # pyglet 2.1 queries the CRTC of disconnected outputs (crtc id 0), which
    # raises a fatal BadRRCrtc X error when a monitor port is unused.
    try:
        from pyglet.libs.x11 import xrandr
        orig = xrandr.XRRGetCrtcInfo
    except (ImportError, AttributeError):
        return

    def get_crtc_info(display, resources, crtc):
        return orig(display, resources, crtc) if crtc else None

    xrandr.XRRGetCrtcInfo = get_crtc_info


# must happen before anything makes pyglet enumerate the screens
work_around_pyglet_xrandr_crash()

from .yagv import App


def main():
    # Disable error checking for increased performance
    pyglet.options['debug_gl'] = False

    App().main()


if __name__ == "__main__":
    main()


# EOF #

{
  inputs = {
    # FIXME: nixos>=23.05 uses pyglet-2, which isn't compatible with 1.5
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-22.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
        pythonPackages = pkgs.python310Packages;
      in rec {
        packages = rec {
          default = yagv;

          yagv = pythonPackages.buildPythonPackage rec {
            pname = "yagv";
            version = "0.5.8";

            src = ./.;

            doCheck = false;

            postFixup = ''
              substituteInPlace $out/bin/yagv \
                --replace 'exec -a "$0"' \
                          'exec -a "$0" nix run --impure github:guibou/nixGL#nixGLIntel -- '
            '';

            nativeBuildInputs = with pkgs; [ makeWrapper ];

            propagatedBuildInputs = with pythonPackages; [
              setuptools
              pyglet
              numpy
            ];
          };
        };
      }
    );
}

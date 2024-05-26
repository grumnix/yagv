{
  inputs = {
    # FIXME: nixos-23.11 uses pyglet-2, which isn't compatible with 1.5
    nixpkgs.url = "github:NixOS/nixpkgs?ref=nixos-24.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonPackages = pkgs.python310Packages;
      in rec {
        packages = rec {
          default = yagv;

          yagv = pythonPackages.buildPythonPackage rec {
            pname = "yagv";
            version = "0.5.8";

            src = ./.;

            doCheck = false;

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

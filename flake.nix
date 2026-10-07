{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
        pythonPackages = pkgs.python3Packages;
      in rec {
        packages = rec {
          default = yagv;

          yagv = pythonPackages.buildPythonPackage rec {
            pname = "yagv";
            version = "0.5.8";

            src = ./.;

            pyproject = true;
            build-system = [ pythonPackages.setuptools ];

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

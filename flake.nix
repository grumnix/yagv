{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-22.05";
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

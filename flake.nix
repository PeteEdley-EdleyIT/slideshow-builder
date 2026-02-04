{
  description = "A Python development environment and Docker image for video automation";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-23.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        pythonEnv = pkgs.python311.withPackages (
          p: with p; [
            numpy
            moviepy
            pillow
            requests
            python-dotenv
            setuptools
            apscheduler
            matrix-nio
            python-olm
            cachetools
            atomicwrites
            peewee
          ]
        );

        appSrc = ./.; # Get all files in the current directory (Flakes only see tracked files)

        appDir = pkgs.stdenv.mkDerivation {
          name = "notices-video-automation-app";
          src = appSrc;
          installPhase = ''
            mkdir -p $out/app
            cp -r * $out/app/
            chmod +x $out/app/setup-docker.sh $out/app/create_slideshow.py
          '';
        };

        rootContents = pkgs.buildEnv {
          name = "root-contents";
          paths = [
            pkgs.bash
            pkgs.ffmpeg
            pkgs.cron
            pkgs.coreutils
            pkgs.gnugrep
            pkgs.gnused
            appDir
          ];
          postBuild = ''
            mkdir -p $out/tmp
            mkdir -p $out/var/run
            mkdir -p $out/var/log
            mkdir -p $out/etc/crontabs
            # Add a basic /etc/passwd for root if needed, though cron usually wants it
            mkdir -p $out/etc
            echo "root:x:0:0:root:/root:/bin/bash" > $out/etc/passwd
            echo "root:x:0:" > $out/etc/group
          '';
        };

      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pkgs.python311
            pkgs.python311Packages.venvShellHook # Keep for local dev convenience
            pkgs.git
            pkgs.ffmpeg
            pythonEnv # Use the defined python environment
          ];
          venvDir = ".venv";
        };

        # Define a Docker image output
        packages.dockerImage = pkgs.dockerTools.buildImage {
          name = "mcf-notices-builder";
          tag = "latest";

          copyToRoot = [ rootContents ];

          config = {
            Cmd = [ "/app/setup-docker.sh" ]; # Execute the setup script
            Entrypoint = [
              "${pkgs.bash}/bin/bash"
              "-c"
            ];
            WorkingDir = "/app";
            Env = [
              "PATH=${
                pkgs.lib.makeBinPath [
                  pythonEnv
                  pkgs.bash
                  pkgs.ffmpeg
                  pkgs.cron
                  pkgs.coreutils
                  pkgs.gnugrep
                  pkgs.gnused
                ]
              }"
              "PYTHONPATH=/app"
              "PYTHONUNBUFFERED=1"
            ];
          };
        };
      }
    );
}

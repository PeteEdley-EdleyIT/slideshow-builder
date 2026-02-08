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

        extraFiles = pkgs.runCommand "extra-files" { } ''
          mkdir -p $out/tmp
          mkdir -p $out/var/run
          mkdir -p $out/var/log
          mkdir -p $out/etc/crontabs
          echo "root:x:0:0:root:/root:/bin/bash" > $out/etc/passwd
          echo "root:x:0:" > $out/etc/group
        '';

        rootContents = pkgs.buildEnv {
          name = "root-contents";
          paths = [
            pkgs.bash
            pkgs.ffmpeg
            pkgs.cron
            pkgs.coreutils
            pkgs.gnugrep
            pkgs.gnused
            pkgs.findutils
            pkgs.imagemagick
            pkgs.dejavu_fonts
            pkgs.fontconfig
            appDir
            extraFiles
          ];
        };

      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pkgs.python311
            pkgs.python311Packages.venvShellHook # Keep for local dev convenience
            pkgs.git
            pkgs.ffmpeg
            pkgs.imagemagick
            pkgs.dejavu_fonts
            pkgs.fontconfig
            pythonEnv # Use the defined python environment
          ];
          venvDir = ".venv";
        };

        # Define a Docker image output
        packages.dockerImage = pkgs.dockerTools.buildImage {
          name = "slideshow-builder";
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
                  pkgs.findutils
                  pkgs.imagemagick
                  pkgs.dejavu_fonts
                  pkgs.fontconfig
                ]
              }"
              "PYTHONPATH=/app"
              "PYTHONUNBUFFERED=1"
              "FONTCONFIG_FILE=${pkgs.fontconfig.out}/etc/fonts/fonts.conf"
              "FONTCONFIG_PATH=${pkgs.fontconfig.out}/etc/fonts"
            ];
            Healthcheck = {
              # Checks if the heartbeat file was updated in the last 2 minutes
              # Note: HEARTBEAT_FILE is defined as /tmp/heartbeat in create_slideshow.py
              Test = [ "CMD-SHELL" "find /tmp/heartbeat -mmin -2" ];
              Interval = 60000000000; # 60s in nanoseconds
              StartPeriod = 30000000000; # 30s in nanoseconds
              Retries = 3;
            };
          };
        };
      }
    );
}

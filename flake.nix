{
  description = "A Python development environment and Docker image for video automation";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-23.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        pythonEnv = pkgs.python311.withPackages (p: with p; [
          numpy
          moviepy
          pillow
          requests
          python-dotenv
        ]);

        appSrc = pkgs.lib.cleanSource ./.; # Get all files in the current directory

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
          name = "notices-video-automation";
          tag = "latest";

          # The contents of the Docker image
          contents = [
            pythonEnv
            pkgs.bash
            pkgs.ffmpeg
            pkgs.cronie # Add cronie for cron daemon
            appSrc
          ];

          config = {
            Cmd = [ "/usr/local/bin/start-cron.sh" ]; # New command to start cron
            Entrypoint = [ "${pkgs.bash}/bin/bash" "-c" ];
            WorkingDir = "/app";
            Env = [
              "PATH=${pkgs.lib.makeBinPath [ pythonEnv pkgs.bash pkgs.ffmpeg pkgs.cronie ]}" # Add cronie to PATH
              "PYTHONUNBUFFERED=1"
            ];
          };

          postInstall = ''
            mkdir -p $out/app
            cp -r ${appSrc}/* $out/app/
            chmod +x $out/app/create_slideshow.py # Make script executable

            # Create cron job file for root user
            mkdir -p $out/etc/crontabs
            echo "*/5 * * * * /app/create_slideshow.py >> /var/log/slideshow_cron.log 2>&1" > $out/etc/crontabs/root
            chmod 0600 $out/etc/crontabs/root

            # Create entrypoint script to start cronie in foreground
            mkdir -p $out/usr/local/bin
            cat > $out/usr/local/bin/start-cron.sh <<EOF
            #!/bin/bash
            echo "Starting cron daemon..."
            # Ensure cronie uses the crontab we created
            crontab -u root $out/etc/crontabs/root
            # Start cronie in foreground, logging to stderr
            exec ${pkgs.cronie}/bin/crond -f -L /dev/stderr
            EOF
            chmod +x $out/usr/local/bin/start-cron.sh
          '';
        };
      }
    );
}
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
            pkgs.cron # Add cronie for cron daemon
            appSrc
          ];

          config = {
            Cmd = [ "/app/setup-docker.sh" ]; # Execute the setup script
            Entrypoint = [ "${pkgs.bash}/bin/bash" "-c" ];
            WorkingDir = "/app";
            Env = [
              "PATH=${pkgs.lib.makeBinPath [ pythonEnv pkgs.bash pkgs.ffmpeg pkgs.cron ]}" # Add cronie to PATH
              "PYTHONUNBUFFERED=1"
            ];
          };
        };
      }
    );
}
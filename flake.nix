{
  description = "A Python development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          # Python interpreter
          pkgs.python311

          # venv and pip are included with python311, but we add the hook
          # for automatic virtual environment management.
          pkgs.python311Packages.venvShellHook

          # System-level dependencies
          pkgs.git
          pkgs.ffmpeg
          pkgs.gemini-cli

          # Python packages managed by Nix
          pkgs.python311Packages.numpy
          pkgs.python311Packages.moviepy
          pkgs.python311Packages.pillow
        ];

        # This hook will create and activate a virtual environment named '.venv'
        # in your project directory when you enter the shell.
        venvDir = ".venv";
      };
    };
}

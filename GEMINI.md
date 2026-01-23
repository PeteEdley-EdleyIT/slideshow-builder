# MCF Notices Video Automation

This project is going to take a folder full of images in a jpeg format, and cobine them together into a video slide show.

Here are a list of required features to work through one by one we will not be moving on to the next feature until the current on is complete and tested.

# Development enviroment
The development enviroment will be a nixos machine and we will developing in python, using gemini-cli.  The development enviroment will be set up using via a nix flake and all project dependancies will be managed by the flake instead of somthing like pip and a venv.

# Deployment
Final deployment will be via a docker image, the script will run via a cron drop within the docker image.

# Features
## Complete
- [x] Initial minimun viable code - This needs to take images stored in a local folder and combine them into a video with each image being displayed for 10 seconds. The video needs to then be written out to another local folder

## TODO
==these are to be carried out one at a time in the order listed and a commit made to git once complted and fully tested==

- [x] Get the slide show to repeat multiple times making the video 10 min long
- [ ] Retrieve image files from nextcloud folder as an option along side local files
- [ ] Save the video file to a nextcloud folder
- [ ] Order image files numerically, placing non-prefixed files at the end of the sequence.


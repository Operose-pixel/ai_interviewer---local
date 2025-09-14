# Use an official Nginx image as a parent image
FROM nginx:alpine

# By default, Nginx looks for a config in /etc/nginx/conf.d/default.conf
# We will mount this file using the docker-compose.yml instead of copying it here.
# We also mount the static content using docker-compose.yml.

# The container will listen on port 80
EXPOSE 80

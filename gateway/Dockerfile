FROM nginx:1.29-alpine

COPY http.conf /etc/nginx/configurations/http.conf
COPY https.conf /etc/nginx/configurations/https.conf
COPY routes.conf /etc/nginx/configurations/routes.conf
COPY start.sh /opt/gateway/start.sh

CMD ["/bin/sh", "/opt/gateway/start.sh"]

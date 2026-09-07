sudo nano /etc/nginx/sites-available/masterarbeit
sudo ln -s /etc/nginx/sites-available/masterarbeit /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default


sudo nginx -t
sudo systemctl restart nginx

server {
    listen 80;
    server_name h2989029.stratoserver.net;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name h2989029.stratoserver.net;

    client_max_body_size 10M;

    ssl_certificate /etc/letsencrypt/live/h2989029.stratoserver.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/h2989029.stratoserver.net/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    
    auth_basic "Restricted Access";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /static {
        alias /home/projects/masterarbeit/static;
    }
}

sudo systemctl daemon-reload
sudo systemctl start masterarbeit
sudo systemctl enable masterarbeit
sudo systemctl status masterarbeit

[Unit]
Description=Masterarbeit
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=root
Group=root
WorkingDirectory=/home/projects/masterarbeit
Environment="PATH=/home/projects/masterarbeit/venv/bin"
Environment="PYTHONPATH=/home/projects/masterarbeit"
Environment="DATABASE_URL=postgresql://test_user:test@localhost:5432/test"
Environment="SECRET_KEY=your-random-secret-key-here"
ExecStart=/home/projects/masterarbeit/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 wsgi:app

[Install]
WantedBy=multi-user.target
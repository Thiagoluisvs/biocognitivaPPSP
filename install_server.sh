#!/bin/bash

# ==============================================================================
# Script de Auto-Instalação: BiocognitivaPPSP (Ubuntu 22.04 / 24.04)
# Execute este script logado como 'root' ou com 'sudo' no seu servidor VPS.
# ==============================================================================

# Cores para o log
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}  Instalador Automático - Plataforma BiocognitivaPPSP ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Verifica se está rodando como root
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Erro: Por favor, execute este script como root (ex: sudo ./install_server.sh)${NC}"
  exit 1
fi

# Variáveis
PROJECT_DIR=$(pwd)
DOMAIN="biocognitiva.local" # O Nginx usará isso como placeholder
APP_NAME="biocognitiva"

echo -e "\n${GREEN}[1/6] Atualizando os pacotes do sistema...${NC}"
apt update && apt upgrade -y

echo -e "\n${GREEN}[2/6] Instalando dependências essenciais (Python, Nginx, Certbot)...${NC}"
apt install -y python3-pip python3-venv nginx certbot python3-certbot-nginx curl

echo -e "\n${GREEN}[3/6] Configurando o ambiente virtual e bibliotecas Python...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
# Instalar bibliotecas necessárias para a aplicação
pip install flask werkzeug gunicorn openpyxl

echo -e "\n${GREEN}[4/6] Configurando o serviço Gunicorn (Processo em 2º plano)...${NC}"
cat <<EOF > /etc/systemd/system/${APP_NAME}.service
[Unit]
Description=Gunicorn instance to serve ${APP_NAME}
After=network.target

[Service]
User=root
Group=www-data
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${PROJECT_DIR}/venv/bin"
ExecStart=${PROJECT_DIR}/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 -m 007 app:app

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl start ${APP_NAME}
systemctl enable ${APP_NAME}

echo -e "\n${GREEN}[5/6] Configurando o Proxy Reverso Nginx...${NC}"
cat <<EOF > /etc/nginx/sites-available/${APP_NAME}
server {
    listen 80;
    server_name _; # Aceita qualquer domínio/IP temporariamente

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Permitir uploads grandes (50MB)
        client_max_body_size 50M;
    }
}
EOF

# Habilita o site removendo o default e criando o symlink
rm -f /etc/nginx/sites-enabled/default
ln -s /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/
systemctl restart nginx

echo -e "\n${GREEN}[6/6] Configurando permissões do banco de dados e uploads...${NC}"
# Garante que a pasta static/uploads exista
mkdir -p static/uploads/documents
# Garante permissões corretas para o servidor web poder salvar arquivos e ler o banco SQLite
chown -R root:www-data ${PROJECT_DIR}
chmod -R 775 ${PROJECT_DIR}/static/uploads
# Se o banco já existir, dar permissão de escrita
if [ -f "biocognitiva.db" ]; then
    chmod 664 biocognitiva.db
fi

echo -e "${BLUE}======================================================${NC}"
echo -e "${GREEN}✅ INSTALAÇÃO CONCLUÍDA COM SUCESSO!${NC}"
echo -e "O seu sistema já deve estar rodando no IP deste servidor."
echo -e "\n${BLUE}Próximos Passos:${NC}"
echo "1. Aponte o seu domínio (ex: sistema.biocognitiva.com.br) para o IP deste servidor no Registro.br"
echo "2. Edite o arquivo /etc/nginx/sites-available/biocognitiva e troque 'server_name _;' pelo seu domínio real."
echo "3. Reinicie o nginx: sudo systemctl restart nginx"
echo "4. Rode o certbot para ativar o HTTPS: sudo certbot --nginx -d seu_dominio.com.br"
echo -e "${BLUE}======================================================${NC}"

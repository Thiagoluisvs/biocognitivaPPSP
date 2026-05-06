# Guia de Implantação (Deploy) - Biocognitiva PPSP

Este documento contém o passo a passo completo para publicar a plataforma `BiocognitivaPPSP` em um servidor VPS (Virtual Private Server) rodando Linux (Ubuntu 22.04 ou 24.04).

---

## 1. O que você precisa antes de começar
- Um **Servidor VPS** recém criado (Hostinger, DigitalOcean, Linode, AWS EC2, etc) com **Ubuntu 22.04/24.04**.
- O **Endereço IP** deste servidor.
- Um **Domínio** (ex: `sistema.biocognitiva.com.br`) já configurado na aba de "DNS" (no Registro.br, Cloudflare, etc) apontando a entrada tipo "A" para o IP do servidor VPS.
- Acesso ao terminal do servidor via SSH.

---

## 2. Transferindo os Arquivos para o Servidor

Você precisa enviar todos os arquivos do seu Macbook para o servidor VPS. Não envie a pasta do ambiente virtual (venv) se existir.

**Opção A: Usando SFTP (FileZilla / Cyberduck)**
1. Baixe o programa [Cyberduck](https://cyberduck.io/) (para Mac).
2. Conecte no servidor usando o IP, usuário (root) e senha.
3. No servidor, navegue até a pasta `/var/www/`.
4. Crie uma pasta chamada `biocognitiva`.
5. Arraste todos os arquivos do seu projeto (`app.py`, `models.py`, `install_server.sh`, pastas `templates` e `static`) para dentro de `/var/www/biocognitiva/`.

**Opção B: Usando SSH / SCP do seu Terminal Mac**
Abra o terminal do seu Mac e rode (substitua pelo IP correto):
```bash
scp -r "/Users/thiago/Desktop/AULA ONLINE" root@IP_DO_SEU_SERVIDOR:/var/www/biocognitiva
```

---

## 3. Instalando e Subindo o Sistema (Script Automático)

Acesse o seu servidor VPS via terminal:
```bash
ssh root@IP_DO_SEU_SERVIDOR
```

Navegue até a pasta onde você enviou os arquivos:
```bash
cd /var/www/biocognitiva
```

Dê permissão de execução para o script instalador e rode-o:
```bash
chmod +x install_server.sh
./install_server.sh
```

O script fará o seguinte automaticamente:
1. Instalará o Python, Nginx e ferramentas SSL.
2. Criará o ambiente virtual isolado e instalará o Flask e Gunicorn.
3. Criará um "Serviço" no Linux. Isso significa que se o servidor desligar, quando ligar o sistema volta sozinho.
4. Configurará o Nginx (porta 80) para ler as rotas do Python, permitindo downloads rápidos e uploads de até 50MB.

Ao final do script, seu sistema já estará disponível ao acessar o IP do servidor pelo navegador.

---

## 4. Configurando o Domínio e HTTPS (Cadeado Seguro)

O sistema de Login e Uploads médicos **exige** conexão segura HTTPS. Após apontar o DNS do domínio para o IP do VPS:

Abra a configuração do Nginx no servidor:
```bash
nano /etc/nginx/sites-available/biocognitiva
```

Procure a linha que diz: `server_name _;`
Troque para o seu domínio (exemplo):
```nginx
server_name sistema.biocognitiva.com.br;
```

Salve e saia (No Nano: `CTRL + X`, depois `Y`, depois `ENTER`).

Reinicie o Nginx:
```bash
systemctl restart nginx
```

### Gerando o Certificado SSL Gratuito
Rode o comando do Certbot para gerar o certificado Let's Encrypt (substituindo pelo seu domínio real):
```bash
certbot --nginx -d sistema.biocognitiva.com.br
```
Siga os passos na tela (informar um email de contato e aceitar os termos). Ele configurará o HTTPS automaticamente.

---

## 5. Como Manter o Sistema no Dia a Dia

**Como ver se o sistema está rodando?**
```bash
systemctl status biocognitiva
```

**Como ver os logs de erro se a tela ficar preta (Error 500)?**
```bash
journalctl -u biocognitiva -n 50 --no-pager
```

**O que fazer quando eu modificar o código no meu Mac e enviar o arquivo novo para lá?**
Sempre que substituir o `app.py`, `models.py` ou os arquivos `.html` no servidor, você precisa avisar o sistema para recarregar o código. Basta rodar:
```bash
systemctl restart biocognitiva
```

---

## 6. Realizando Backups do Banco de Dados

Como a arquitetura usa **SQLite**, todos os cadastros, senhas e registros do sistema estão salvos em um único arquivo: `biocognitiva.db`.

Para fazer backup seguro de todos os dados do sistema, basta fazer o download (via Cyberduck ou linha de comando) do arquivo `biocognitiva.db`. 
Recomenda-se realizar isso semanalmente ou configurar um "Cron Job" para enviar esse arquivo automaticamente para uma nuvem/email.

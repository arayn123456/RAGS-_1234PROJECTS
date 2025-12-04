# Docker Deployment Guide - Document Q&A

## Quick Start (Local)

```bash
# Build and run locally
docker-compose up --build

# Access at http://localhost:8000
```

---

## Deploy to Docker Hub

### Step 1: Build the Image
```bash
docker-compose build --no-cache
```

### Step 2: Tag the Image
```bash
docker tag rags-app YOUR_DOCKERHUB_USERNAME/document-qa:latest
```

### Step 3: Login and Push
```bash
docker login
docker push YOUR_DOCKERHUB_USERNAME/document-qa:latest
```

---

## Deploy to EC2 (or any server)

### Step 1: Pull the Image
```bash
docker pull YOUR_DOCKERHUB_USERNAME/document-qa:latest
```

### Step 2: Run the Container
```bash
docker run -d -p 8089:8000 \
  -e "OPENAI_API_KEY=sk-proj-YOUR-API-KEY-HERE" \
  -v /root/data:/app/data \
  --name document-qa \
  YOUR_DOCKERHUB_USERNAME/document-qa:latest
```

### Step 3: Verify
```bash
# Check container is running
docker ps

# Check logs
docker logs document-qa

# Check health
curl http://localhost:8089/health
```

---

## Troubleshooting

### Issue 1: Upload Stuck / API Calls Pending

**Symptom**: Upload button shows "Uploading..." forever, Network tab shows requests as "Pending"

**Cause**: Frontend is calling wrong port (e.g., `localhost:8000` instead of server IP)

**Solution**: 
- The frontend uses relative URLs (`API_URL = ''`)
- This makes API calls go to the same host/port automatically
- If you hardcode an IP, make sure the port matches your Docker mapping!

**Fix if needed**:
```javascript
// In frontend/src/App.jsx
const API_URL = ''  // Empty = relative URLs (recommended)
// OR
const API_URL = 'http://YOUR_SERVER_IP:8089'  // Match your -p port
```

After changing, rebuild and redeploy:
```bash
# Local
docker-compose build --no-cache
docker tag rags-app YOUR_USERNAME/document-qa:latest
docker push YOUR_USERNAME/document-qa:latest

# On server
docker stop document-qa && docker rm document-qa
docker rmi YOUR_USERNAME/document-qa:latest
docker pull YOUR_USERNAME/document-qa:latest
docker run -d -p 8089:8000 -e "OPENAI_API_KEY=..." --name document-qa YOUR_USERNAME/document-qa:latest
```

---

### Issue 2: OpenAI API Key Not Working

**Symptom**: Document upload fails, logs show API errors

**Cause**: API key not passed correctly or invalid

**Solution**:
```bash
# Use quotes around the API key!
docker run -d -p 8089:8000 \
  -e "OPENAI_API_KEY=sk-proj-YOUR-FULL-KEY-HERE" \
  ...
```

**Verify key is set**:
```bash
docker exec document-qa env | grep OPENAI
```

---

### Issue 3: Container Exits Immediately

**Symptom**: `docker ps` shows no running container

**Solution**:
```bash
# Check why it exited
docker logs document-qa

# Common fixes:
# - Missing API key
# - Port already in use (change -p 8090:8000)
# - Not enough memory (upgrade EC2 instance)
```

---

### Issue 4: Data Not Persisting

**Symptom**: Documents disappear after container restart

**Solution**: Mount a volume for data persistence:
```bash
docker run -d -p 8089:8000 \
  -e "OPENAI_API_KEY=..." \
  -v /path/to/data:/app/data \
  --name document-qa \
  YOUR_USERNAME/document-qa:latest
```

---

### Issue 5: Out of Memory

**Symptom**: Container crashes during document processing

**Cause**: EC2 instance too small (t2.micro = 1GB RAM)

**Solution**: 
- Use t2.small (2GB) or t2.medium (4GB)
- Or add swap space:
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## Useful Commands

```bash
# View running containers
docker ps

# View all containers (including stopped)
docker ps -a

# View logs
docker logs document-qa
docker logs -f document-qa  # Follow logs

# Stop container
docker stop document-qa

# Remove container
docker rm document-qa

# Remove image (to force fresh pull)
docker rmi YOUR_USERNAME/document-qa:latest

# Enter container shell
docker exec -it document-qa /bin/bash

# Check container resource usage
docker stats document-qa

# Restart container
docker restart document-qa
```

---

## Port Mapping Reference

```
-p HOST_PORT:CONTAINER_PORT
-p 8089:8000  →  Access via http://SERVER_IP:8089
-p 80:8000    →  Access via http://SERVER_IP (no port needed)
-p 443:8000   →  For HTTPS (needs SSL setup)
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |

---

## Security Notes

1. **Never commit API keys** - Use environment variables
2. **Use HTTPS in production** - Set up SSL/nginx
3. **Restrict ports** - Only expose necessary ports in EC2 security group
4. **Keep images updated** - Regularly rebuild with latest dependencies

---

## Example: Full EC2 Deployment

```bash
# 1. SSH into EC2
ssh -i your-key.pem ubuntu@YOUR_EC2_IP

# 2. Install Docker (if not installed)
sudo apt update
sudo apt install docker.io -y
sudo systemctl start docker
sudo usermod -aG docker $USER

# 3. Pull and run
docker pull dpcode72/document-qa:latest

docker run -d -p 80:8000 \
  -e "OPENAI_API_KEY=sk-proj-YOUR-KEY" \
  -v ~/document-qa-data:/app/data \
  --name document-qa \
  --restart unless-stopped \
  dpcode72/document-qa:latest

# 4. Access at http://YOUR_EC2_PUBLIC_IP
```

---

## Need Help?

Check logs first:
```bash
docker logs document-qa --tail 100
```

Common log messages:
- `OpenAI API key not found` → Set the environment variable
- `Connection refused` → Check port mapping
- `Out of memory` → Upgrade instance or add swap


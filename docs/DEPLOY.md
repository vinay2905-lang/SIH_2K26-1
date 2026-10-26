# Hosting PRAMAAN on the web

PRAMAAN runs as five containers:
- PostgreSQL;
- the API;
- a background worker;
- nginx with the React app;
- Caddy for HTTPS.

The simplest reliable host is **one Linux virtual machine (VM)** running Docker. One script sets everything up and gets a free, auto-renewing HTTPS certificate. You end up with a link like `https://pramaan-sih.centralindia.cloudapp.azure.com` that anyone can open.

| What you need | Why |
|---|---|
| A VM with **2 vCPU and 4 GB RAM**, Ubuntu 22.04 or 24.04 | Document reading (OCR, PDF rendering) needs real CPU; 2 GB works for light use |
| Ports **22, 80, 443** open | SSH, and HTTP/HTTPS for the certificate and the site |
| A hostname pointing at the VM | Required for HTTPS. Azure gives you one for free (step 3). |

> Free "web app" tiers such as Render's free plan are too small for this app: 0.1 CPU, 512 MB, and no disk that survives a restart. Reading the demo documents alone would take many minutes.

## Option A: Azure for Students (free credit, no credit card)

[Azure for Students](https://azure.microsoft.com/free/students) gives US$100 of credit for 12 months to anyone with a college email address, with no credit card. A `Standard_B2s` VM costs roughly US$30–40 a month, so the credit covers about three months of running it non-stop. It lasts much longer if you stop the VM when you are not demoing (see **Costs** below).

### 1. Activate the student subscription

1. Open https://azure.microsoft.com/free/students and choose **Start free**.
2. Sign in with your **college email**.

Choose the student offer itself. A university account that has used the general 30-day Azure free trial can't activate Azure for Students afterwards.

### 2. Create the virtual machine

In the [Azure portal](https://portal.azure.com), go to **Create a resource → Virtual machine** and fill in the form:

| Field | Value |
|---|---|
| Subscription | Azure for Students |
| Resource group | **Create new** → `pramaan` |
| Virtual machine name | `pramaan` |
| Region | **(Asia Pacific) Central India**. If you get a policy error, pick another region your subscription allows. |
| Image | **Ubuntu Server 24.04 LTS – x64 Gen2** |
| Size | **Standard_B2s** (2 vCPU, 4 GiB) |
| Authentication type | **Password** (simplest) – username `azureuser` and a strong password |
| Public inbound ports | **Allow selected ports** → tick **SSH (22)**, **HTTP (80)**, **HTTPS (443)** |

Click **Review + create**, then **Create**. It takes a minute or two.

### 3. Give it a hostname

1. Open the VM's **Overview** page.
2. Next to **DNS name**, click **Not configured** (or **Configure**).
3. Type a label such as `pramaan-sih` and click **Save**.

Your hostname is now `pramaan-sih.<region>.cloudapp.azure.com`, for example `pramaan-sih.centralindia.cloudapp.azure.com`. Copy it from the Overview page.

### 4. Connect to the VM

On Windows, open **Command Prompt** (Windows 10/11 include `ssh`):

```bat
ssh azureuser@pramaan-sih.centralindia.cloudapp.azure.com
```

Type `yes` the first time, then your password.

### 5. Install PRAMAAN

Run these on the VM, using your own hostname:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone -b claude/stoic-mayer-utvdia https://github.com/vinay2905-lang/SIH_2K26-1.git pramaan
cd pramaan
sudo bash deploy/setup.sh --domain pramaan-sih.centralindia.cloudapp.azure.com --demo
```

The script does the following:
- installs Docker;
- creates `.env` with random secrets;
- builds and starts all containers;
- gets the HTTPS certificate;
- loads the synthetic demo data (`--demo`).

The first run takes roughly 10–15 minutes. Most of that is building the images.

### 6. Open it

Go to `https://pramaan-sih.centralindia.cloudapp.azure.com`. The sign-in page lists the demo accounts; the password for all of them is `Pramaan@2026`.

## Option B: any other Linux server

The same script works on any Ubuntu/Debian server with ports 22, 80 and 443 open, for example:
- DigitalOcean (the GitHub Student Developer Pack includes credit);
- AWS Lightsail;
- Oracle Cloud's Always Free VMs;
- a college server.

If you have no domain name, use the free `sslip.io` hostname that matches the server's public IP. For IP `20.40.60.80`, that is `20-40-60-80.sslip.io`:

```bash
sudo bash deploy/setup.sh --domain 20-40-60-80.sslip.io --demo
```

Without `--domain`, the site runs on plain HTTP at `http://<server-ip>:8080`. Then open port 8080 in the firewall, not 80/443. Browsers will show it as "Not secure".

## Day-to-day commands

Run these on the server, inside the `pramaan` folder.

| Task | Command |
|---|---|
| See status | `sudo docker compose ps` |
| Follow logs | `sudo docker compose logs -f api worker` |
| Update to the latest code | `git pull && sudo docker compose up -d --build` |
| Reset the demo data | `sudo bash deploy/reset-demo.sh` |
| Stop everything | `sudo docker compose down` (data is kept) |
| Start again | `sudo docker compose up -d` |

### Reset the demo every night (optional)

Visitors can change the demo data: approving applications, publishing rules, and so on. To restore it every morning, run `sudo crontab -e` and add this line. It runs at 02:30 server time; Azure servers use UTC, so that is 08:00 IST.

```
30 2 * * * cd /home/azureuser/pramaan && bash deploy/reset-demo.sh >> /var/log/pramaan-reset.log 2>&1
```

## Costs

- **Stop the VM when not in use.** In the Azure portal, click **Stop** on the VM so its status reads *Stopped (deallocated)*. Compute charges stop; only the small disk and IP charges continue.
- Start it again before a demo. The hostname stays the same, and the containers start by themselves. Give it about two minutes.
- To see how much credit is left, search the Azure portal for **Education** and open the Education hub.

## Things to know before sharing the link

- **Anyone with the link can sign in as any demo account**, including the senior officer and rule admin. That's what you want for judges and reviewers. Upload only synthetic documents, never real ones.
- **Hide the demo list.** To stop listing the demo accounts on the sign-in page, set `PRAMAAN_SHOW_DEMO_LOGINS=false` in `.env` and run `sudo docker compose up -d`.
- **Secrets.** `.env` holds the database password, the document-encryption key and the token-signing secret. Keep it private.
  - If you lose the encryption key, the stored documents can't be decrypted.
  - If you rebuild the server, copy `.env` across.
- **Issuer verification.** The fire, land, university, NBA and payment checks use the built-in sandbox, not real government services.

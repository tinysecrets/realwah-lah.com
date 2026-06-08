# Wah-Lah Deploy Sequence

## One-time setup

1. Create a Fly token:
   ```bash
   flyctl tokens create deploy --app wah-lah --name github-wahlah-deploy
   ```

2. Add it to GitHub:
   `Settings -> Secrets and variables -> Actions -> New repository secret`

   Name:
   ```text
   FLY_API_TOKEN
   ```

3. In Cloudflare DNS, keep these records:
   ```text
   wah-lah.com      A/AAAA or CNAME -> Fly app
   www.wah-lah.com  A/AAAA or CNAME -> Fly app
   api.wah-lah.com  A/AAAA or CNAME -> Fly app
   ```

## Normal deploy

Save and push changes:

```bash
scripts/save_and_push.sh "Describe the change"
```

GitHub Actions deploys automatically on every push to `main`.

## Direct deploy from a machine with Fly auth

```bash
scripts/deploy_wahlah.sh
```

The script deploys, requests custom-domain certificates, and checks:

```text
https://wah-lah.com/api/health
https://wah-lah.fly.dev/api/health
```

## Current recovery note

The domain registration is active through Cloudflare Registrar until
`2027-04-22`. If deployment fails with `no access token available`, the GitHub
repository is missing the `FLY_API_TOKEN` secret.

The Fly app name is `wah-lah`.

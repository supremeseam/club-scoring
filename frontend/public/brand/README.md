# Club branding files

Put your club's logo files here, for example `logo.png` (full logo), `burgee.png` (flag alone) and
`favicon.png`, then point the settings at them in `.env`:

```
CLUB_LOGO_URL=/brand/logo.png
CLUB_BURGEE_URL=/brand/burgee.png
```

The files in this folder are **not tracked by git** (they belong to your club, not to the open-source
project). Without them the app shows a plain pennant and your club name.

- **Development:** the files are served straight from this folder.
- **Production (`compose.yml`):** this folder is mounted into the web and app containers, so just upload your
  files to `frontend/public/brand/` on the server. No rebuild is needed to change a logo.
- Use **PNG or JPG** for the full logo so it also appears at the top of the printed PDFs.

// Root postinstall: create .env, install the front end, then sync the Python env (needs uv).
import { spawnSync } from "node:child_process";

const run = (cmd, args) => spawnSync(cmd, args, { stdio: "inherit", shell: true }).status === 0;

await import("./ensure-env.mjs");
if (!run("npm", ["--prefix", "frontend", "install"])) process.exit(1);

if (spawnSync("python", ["-m", "uv", "--version"], { shell: true, stdio: "ignore" }).status !== 0) {
  console.error(
    "\nuv (the Python package manager) was not found on your PATH.\n" +
      "Front-end packages are installed. Run: python -m pip install uv   then: npm run setup:py\n" +
      "  Windows:  winget install --id=astral-sh.uv -e      (or: pip install uv)\n" +
      "  macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh\n",
  );
  process.exit(0);
}
if (!run("python", ["-m", "uv", "sync", "--project", "backend"])) process.exit(1);

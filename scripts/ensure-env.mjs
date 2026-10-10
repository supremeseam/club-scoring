// Create .env from .env.example on first run so local startup needs no manual step.
import { copyFileSync, existsSync } from "node:fs";

if (!existsSync(".env") && existsSync(".env.example")) {
  copyFileSync(".env.example", ".env");
  console.log("Created .env from .env.example (local development defaults).");
}

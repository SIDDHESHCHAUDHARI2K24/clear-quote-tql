// openapi-typescript emits its own "auto-generated" comment but not the
// `// GENERATED FILE` banner every generated file in this repo is expected
// to carry (see AGENTS.md project map: "generated from the FastAPI OpenAPI
// schema; never hand-edit"). This script prepends it after generation so
// `pnpm --filter @cq/api-client run generate` produces the pinned banner
// without hand-editing schema.d.ts.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const target = fileURLToPath(new URL("../src/schema.d.ts", import.meta.url));
const banner = "// GENERATED FILE — run `make api-client` to regenerate. Do not hand-edit.\n";

const current = readFileSync(target, "utf8");
if (!current.startsWith(banner)) {
  writeFileSync(target, banner + current);
}

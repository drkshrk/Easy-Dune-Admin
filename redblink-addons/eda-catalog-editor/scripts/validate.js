#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const manifestPath = path.join(repoRoot, "addon.json");
const allowedPermissions = new Set([
  "players:read",
  "database:read",
  "database:write",
  "server:status",
  "server:restart",
  "files:addon-data",
  "broadcast:send"
]);

function fail(message) {
  console.error(`Validation failed: ${message}`);
  process.exit(1);
}

function normalizePermissions(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  if (typeof value !== "object") fail("permissions must be an object or array.");
  const normalized = [];
  for (const [scope, actions] of Object.entries(value)) {
    if (!Array.isArray(actions)) fail(`permissions.${scope} must be an array.`);
    for (const action of actions) normalized.push(`${scope}:${action}`);
  }
  return normalized;
}

function requireString(manifest, field) {
  if (typeof manifest[field] !== "string" || !manifest[field].trim()) fail(`${field} must be a non-empty string.`);
}

function main() {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  if (manifest.schemaVersion !== 1) fail("schemaVersion must be 1.");
  for (const field of ["id", "name", "description", "author", "version"]) requireString(manifest, field);
  if (!/^[a-z0-9][a-z0-9-]{2,63}$/.test(manifest.id)) fail("id must be lowercase, URL-safe, and 3-64 characters.");
  if (manifest.type !== "ui") fail("type must be ui.");
  if (!manifest.entry || typeof manifest.entry !== "object") fail("entry must be an object.");
  if (!manifest.entry.navigation || !manifest.entry.path) fail("entry.navigation and entry.path are required.");
  if (manifest.entry.path.startsWith("/") || manifest.entry.path.includes("..")) fail("entry.path must be a relative path inside the addon package.");
  if (!fs.existsSync(path.resolve(repoRoot, manifest.entry.path))) fail(`entry.path does not exist: ${manifest.entry.path}`);
  for (const permission of normalizePermissions(manifest.permissions)) {
    if (!allowedPermissions.has(permission)) fail(`unsupported permission: ${permission}`);
  }
  for (const requiredFile of ["web/catalog.json", "web/base-unknown.png", "web/base-schematic.png", "web/base-augment.png"]) {
    if (!fs.existsSync(path.join(repoRoot, requiredFile))) fail(`missing required file: ${requiredFile}`);
  }
  console.log(`Addon manifest is valid: ${manifest.id} ${manifest.version}`);
}

main();

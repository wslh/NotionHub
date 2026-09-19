"use strict";
/**
 * NotionHub VS Code extension.
 *
 * Thin wrapper around the existing NotionHub Python CLI
 * (`notionhub` console script installed via `pip install -e .`).
 *
 * Each command spawns the CLI as a subprocess, streams stdout/stderr into
 * an Output Channel called "NotionHub", and reports the exit code as a
 * notification. No Node-side business logic.
 */
const { spawn } = require("child_process");
const vscode = require("vscode");

let outputChannel = null;

function ensureChannel() {
  if (!outputChannel) {
    outputChannel = vscode.window.createOutputChannel("NotionHub");
  }
  return outputChannel;
}

function getConfig() {
  return vscode.workspace.getConfiguration("notionhub");
}

function resolveCwd() {
  const cfgCwd = getConfig().get("workingDirectory", "");
  if (cfgCwd && cfgCwd.trim()) {
    return cfgCwd;
  }
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    return folders[0].uri.fsPath;
  }
  return process.cwd();
}

function buildEnv() {
  const env = Object.assign({}, process.env);
  const envFile = getConfig().get("envFile", "");
  if (envFile && envFile.trim()) {
    env.NOTIONHUB_ENV_FILE = envFile;
  }
  return env;
}

/**
 * Run a NotionHub CLI subcommand and stream output.
 * @param {string} command the CLI subcommand (sync, check, status, plugins, ...)
 * @param {string[]} args extra CLI args
 * @param {object} [opts]
 * @param {string} [opts.successMessage] override the success notification text
 */
function runCli(command, args = [], opts = {}) {
  const channel = ensureChannel();
  channel.show(true);
  const cfg = getConfig();
  const pythonPath = cfg.get("pythonPath", "notionhub") || "notionhub";
  const fullArgs = [command, ...args];
  channel.appendLine(`> ${pythonPath} ${fullArgs.join(" ")}`);

  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(pythonPath, fullArgs, {
        env: buildEnv(),
        cwd: resolveCwd(),
        shell: false,
      });
    } catch (err) {
      channel.appendLine(`[spawn error] ${err && err.message}`);
      vscode.window.showErrorMessage(
        `NotionHub: cannot start '${pythonPath}' - ${err && err.message}`
      );
      resolve({ code: -1, stdout: "", stderr: String(err) });
      return;
    }

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      const text = chunk.toString();
      stdout += text;
      channel.append(text);
    });
    child.stderr.on("data", (chunk) => {
      const text = chunk.toString();
      stderr += text;
      channel.append(text);
    });
    child.on("error", (err) => {
      channel.appendLine(`[spawn error] ${err && err.message}`);
      vscode.window.showErrorMessage(
        `NotionHub: '${pythonPath}' not found on PATH. Install with 'pip install -e .' or set notionhub.pythonPath.`
      );
      resolve({ code: -1, stdout, stderr: stderr + "\n" + (err && err.message) });
    });
    child.on("close", (code) => {
      channel.appendLine(`\n[exit ${code}]`);
      const ok = code === 0;
      const message =
        (opts.successMessage || `NotionHub: ${command} OK`) + (ok ? "" : ` (exit ${code})`);
      if (ok) {
        vscode.window.showInformationMessage(message);
      } else {
        vscode.window.showErrorMessage(message);
      }
      resolve({ code, stdout, stderr });
    });
  });
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("notionhub.sync", () =>
      runCli("sync", ["--quiet"], { successMessage: "NotionHub: sync completed" })
    )
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("notionhub.check", () =>
      runCli("check", [], { successMessage: "NotionHub: check passed" })
    )
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("notionhub.status", () =>
      runCli("status", [], { successMessage: "NotionHub: status OK" })
    )
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("notionhub.plugins", () =>
      runCli("plugins", ["list"], { successMessage: "NotionHub: plugins listed" })
    )
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("notionhub.openSettings", () =>
      vscode.commands.executeCommand("workbench.action.openSettings", "notionhub")
    )
  );

  context.subscriptions.push({
    dispose: () => {
      if (outputChannel) {
        outputChannel.dispose();
        outputChannel = null;
      }
    },
  });
}

function deactivate() {
  if (outputChannel) {
    outputChannel.dispose();
    outputChannel = null;
  }
}

module.exports = {
  activate,
  deactivate,
};
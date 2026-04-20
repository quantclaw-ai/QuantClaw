import express from "express";
import OpenAI from "openai";
import Anthropic from "@anthropic-ai/sdk";
import { GoogleGenAI } from "@google/genai";
import { readFileSync, existsSync } from "fs";
import { homedir } from "os";
import { join } from "path";

const app = express();
app.use(express.json({ limit: "10mb" }));

const PORT = 24122;

// ── Load OAuth credentials ──

function loadOAuthCredentials() {
  const paths = [
    join(process.cwd(), "data", "oauth_credentials.json"),
    join(process.cwd(), "..", "data", "oauth_credentials.json"),
  ];
  for (const p of paths) {
    if (existsSync(p)) {
      return JSON.parse(readFileSync(p, "utf8"));
    }
  }
  return {};
}

function loadGeminiCliCredentials() {
  const p = join(homedir(), ".gemini", "oauth_creds.json");
  if (existsSync(p)) {
    return JSON.parse(readFileSync(p, "utf8"));
  }
  return null;
}

// ── Provider error formatting ──
//
// SDK errors hide the HTTP status + response body inside .status / .response.
// The default `err.message` is often "400 status code (no body)" which gives
// the operator nothing to act on. This helper digs out everything we can find.
function formatProviderError(provider, model, err) {
  const status = err?.status ?? err?.statusCode ?? "?";
  // Anthropic SDK exposes structured error info on .error; OpenAI on .response.
  let body = "";
  try {
    if (err?.response?.text) body = err.response.text.slice(0, 240);
    else if (err?.body && typeof err.body === "string") body = err.body.slice(0, 240);
    else if (err?.error) body = JSON.stringify(err.error).slice(0, 240);
  } catch {}
  const baseMsg = err?.message || String(err);
  return `${provider} ${status} (model=${model}): ${baseMsg}${body ? " | body=" + body : ""}`;
}

// ── OpenAI (Codex/subscription via chatgpt.com) ──

// Models the Codex backend accepts. Standard OpenAI ids like "gpt-4o" are
// NOT valid here — the Codex endpoint speaks its own model namespace and
// returns 400 with an empty body when given an unknown name. So we map any
// non-Codex request down to a sensible default.
const CODEX_MODEL_PREFIXES = ["gpt-5", "gpt-4.1", "gpt-4o-codex", "o1", "o3", "codex"];
const CODEX_DEFAULT_MODEL = "gpt-5.4";

function resolveCodexModel(requested) {
  if (!requested) return CODEX_DEFAULT_MODEL;
  const lower = String(requested).toLowerCase();
  if (CODEX_MODEL_PREFIXES.some((p) => lower.startsWith(p))) return requested;
  return CODEX_DEFAULT_MODEL;
}

async function handleOpenAI(req, res) {
  const { model, messages, system_prompt, access_token } = req.body;
  if (!access_token) return res.json({ error: "No OpenAI OAuth token" });

  // Extract account ID from JWT
  let accountId = "";
  try {
    const payload = JSON.parse(
      Buffer.from(access_token.split(".")[1], "base64url").toString()
    );
    accountId =
      payload?.["https://api.openai.com/auth"]?.chatgpt_account_id || "";
  } catch {}

  const client = new OpenAI({
    apiKey: access_token,
    baseURL: "https://chatgpt.com/backend-api/codex",
    defaultHeaders: {
      "chatgpt-account-id": accountId,
      originator: "quantclaw",
      "OpenAI-Beta": "responses=experimental",
    },
  });

  const useModel = resolveCodexModel(model);
  try {
    const input = messages.filter((m) => m.role !== "system");
    const response = await client.responses.create({
      model: useModel,
      instructions: system_prompt || "",
      input,
      store: false,
      stream: true,
    });
    // Collect streamed output
    let outputText = "";
    for await (const event of response) {
      if (event.type === "response.output_text.delta") {
        outputText += event.delta || "";
      } else if (event.type === "response.completed") {
        outputText = event.response?.output_text || outputText;
      }
    }
    res.json({
      response: outputText,
      model: useModel,
      requested_model: model,
      provider: "openai-oauth",
    });
  } catch (err) {
    res.json({ error: formatProviderError("OpenAI Codex", useModel, err) });
  }
}

// ── Anthropic (OAuth via Bearer + beta headers) ──

async function handleAnthropic(req, res) {
  const { model, messages, system_prompt, access_token } = req.body;
  if (!access_token) return res.json({ error: "No Anthropic OAuth token" });

  const client = new Anthropic({
    apiKey: null,
    authToken: access_token,
    defaultHeaders: {
      "anthropic-beta": "claude-code-20250219,oauth-2025-04-20",
      "user-agent": "quantclaw/0.1.0",
      "x-app": "cli",
    },
  });

  try {
    const anthropicMessages = messages.filter((m) => m.role !== "system");
    const response = await client.messages.create({
      model: model || "claude-sonnet-4-6",
      max_tokens: 4096,
      system: system_prompt || "",
      messages: anthropicMessages,
    });
    const content = response.content
      .filter((b) => b.type === "text")
      .map((b) => b.text)
      .join("");
    res.json({
      response: content,
      model: model,
      provider: "anthropic-oauth",
    });
  } catch (err) {
    res.json({ error: formatProviderError("Anthropic", model || "claude-sonnet-4-6", err) });
  }
}

// ── Google Gemini (OAuth via google-genai SDK) ──

async function handleGoogle(req, res) {
  const { model, messages, system_prompt, access_token, refresh_token } =
    req.body;

  // Build credentials - prefer passed tokens, fallback to Gemini CLI creds
  let refreshToken = refresh_token;
  let accessToken = access_token;

  if (!refreshToken) {
    const geminiCreds = loadGeminiCliCredentials();
    if (geminiCreds) {
      refreshToken = geminiCreds.refresh_token;
      accessToken = geminiCreds.access_token;
    }
  }

  if (!refreshToken && !accessToken) {
    return res.json({ error: "No Google OAuth credentials" });
  }

  // Set GEMINI_OAUTH_CLIENT_ID / GEMINI_OAUTH_CLIENT_SECRET via env or .env.
  // The published Gemini CLI installed-app credentials work here; see README.
  const CLIENT_ID = process.env.GEMINI_OAUTH_CLIENT_ID || "";
  const CLIENT_SECRET = process.env.GEMINI_OAUTH_CLIENT_SECRET || "";
  if (!CLIENT_ID || !CLIENT_SECRET) {
    return res.json({
      error:
        "Google OAuth client not configured. Set GEMINI_OAUTH_CLIENT_ID and " +
        "GEMINI_OAUTH_CLIENT_SECRET in your .env (see .env.example).",
    });
  }

  // Refresh the token first
  try {
    const tokenResp = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: CLIENT_ID,
        client_secret: CLIENT_SECRET,
        refresh_token: refreshToken,
        grant_type: "refresh_token",
      }),
    });
    const tokenData = await tokenResp.json();
    if (tokenData.access_token) {
      accessToken = tokenData.access_token;
    }
  } catch {}

  // Use the Google GenAI SDK with OAuth credentials
  try {
    const ai = new GoogleGenAI({
      vertexai: false,
      httpOptions: {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      },
    });

    // Build contents
    const contents = messages
      .filter((m) => m.role !== "system")
      .map((m) => ({
        role: m.role === "assistant" ? "model" : "user",
        parts: [{ text: m.content }],
      }));

    const response = await ai.models.generateContent({
      model: model || "gemini-2.5-flash",
      contents,
      config: {
        systemInstruction: system_prompt || undefined,
      },
    });

    res.json({
      response: response.text || "",
      model: model,
      provider: "google-oauth",
    });
  } catch (err) {
    // If SDK doesn't support this auth method, try raw fetch like OpenClaw
    try {
      const resp = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${model || "gemini-2.5-flash"}:generateContent`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            system_instruction: system_prompt
              ? { parts: [{ text: system_prompt }] }
              : undefined,
            contents: messages
              .filter((m) => m.role !== "system")
              .map((m) => ({
                role: m.role === "assistant" ? "model" : "user",
                parts: [{ text: m.content }],
              })),
          }),
        }
      );
      const data = await resp.json();
      if (resp.ok) {
        const text =
          data?.candidates?.[0]?.content?.parts?.[0]?.text || "";
        return res.json({
          response: text,
          model: model,
          provider: "google-oauth",
        });
      }
      res.json({
        error: data?.error?.message || `Gemini error ${resp.status}`,
      });
    } catch (err2) {
      res.json({ error: err.message + " | fallback: " + err2.message });
    }
  }
}

// ── Routes ──

app.post("/chat/openai", handleOpenAI);
app.post("/chat/anthropic", handleAnthropic);
app.post("/chat/google", handleGoogle);

app.get("/health", (req, res) => {
  const creds = loadOAuthCredentials();
  res.json({
    status: "ok",
    providers: Object.keys(creds),
    gemini_cli: !!loadGeminiCliCredentials(),
  });
});

app.listen(PORT, () => {
  console.log(`QuantClaw sidecar running on http://localhost:${PORT}`);
});

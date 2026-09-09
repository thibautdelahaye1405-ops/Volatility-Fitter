/* MCP Apps postMessage bridge (ext-apps spec 2026-01-26), dependency-free.
 *
 * Inlined into every ui://volfit/... page by tools_charts._html. The host
 * renders the page in a sandboxed iframe; all traffic is plain JSON-RPC 2.0
 * objects over window.parent.postMessage. The bridge performs the
 * ui/initialize handshake, delivers tool-input / tool-result / host-context
 * notifications to the page, answers ping + resource-teardown, and exposes
 * the app-initiated requests (tools/call, ui/message, ui/open-link,
 * ui/request-display-mode, ui/notifications/size-changed).
 */
window.VolfitBridge = (function () {
  var nextId = 1;
  var pending = {};
  var handlers = {};
  var hostContext = { theme: "light", displayMode: "inline" };

  function post(msg) {
    try { window.parent.postMessage(msg, "*"); } catch (e) { /* no host */ }
  }
  function request(method, params) {
    var id = nextId++;
    return new Promise(function (resolve, reject) {
      pending[id] = { resolve: resolve, reject: reject };
      post({ jsonrpc: "2.0", id: id, method: method, params: params || {} });
    });
  }
  function notify(method, params) {
    post({ jsonrpc: "2.0", method: method, params: params || {} });
  }
  function emit(name, payload) {
    (handlers[name] || []).forEach(function (fn) { try { fn(payload); } catch (e) { console.error(e); } });
  }

  window.addEventListener("message", function (ev) {
    var m = ev.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id !== undefined && m.method === undefined) {           // a response to us
      var p = pending[m.id]; delete pending[m.id];
      if (!p) return;
      if (m.error) p.reject(m.error); else p.resolve(m.result);
      return;
    }
    switch (m.method) {
      case "ui/notifications/tool-input": emit("toolInput", m.params || {}); break;
      case "ui/notifications/tool-input-partial": emit("toolInputPartial", m.params || {}); break;
      case "ui/notifications/tool-result": emit("toolResult", m.params || {}); break;
      case "ui/notifications/tool-cancelled": emit("toolCancelled", m.params || {}); break;
      case "ui/notifications/host-context-changed":
        hostContext = Object.assign({}, hostContext, m.params || {});
        emit("hostContext", hostContext); break;
      case "ping":
        if (m.id !== undefined) post({ jsonrpc: "2.0", id: m.id, result: {} }); break;
      case "ui/resource-teardown":
      case "ui/notifications/request-teardown":
        emit("teardown", m.params || {});
        if (m.id !== undefined) post({ jsonrpc: "2.0", id: m.id, result: {} }); break;
      default: break;
    }
  });

  return {
    on: function (name, fn) { (handlers[name] = handlers[name] || []).push(fn); return this; },
    context: function () { return hostContext; },
    init: function (name) {
      // Exactly the three fields the ext-apps host schema validates:
      // appInfo (not clientInfo), appCapabilities, protocolVersion.
      return request("ui/initialize", {
        appInfo: { name: name || "volfit-app", version: "0.1.0" },
        appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] },
        protocolVersion: "2026-01-26"
      }).then(function (res) {
        hostContext = Object.assign({}, hostContext, (res && res.hostContext) || {});
        notify("ui/notifications/initialized", {});
        emit("hostContext", hostContext);
        return res;
      }, function () { emit("hostContext", hostContext); return null; });
    },
    sizeChanged: function (w, h) { notify("ui/notifications/size-changed", { width: w, height: h }); },
    callTool: function (name, args) { return request("tools/call", { name: name, arguments: args || {} }); },
    sendMessage: function (text) {
      return request("ui/message", { role: "user", content: { type: "text", text: text } });
    },
    openLink: function (url) { return request("ui/open-link", { url: url }); },
    requestDisplayMode: function (mode) { return request("ui/request-display-mode", { mode: mode }); },
    updateModelContext: function (text) {
      return request("ui/update-model-context", { content: [{ type: "text", text: text }] });
    }
  };
})();

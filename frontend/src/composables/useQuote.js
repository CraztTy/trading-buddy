import { ref, onUnmounted, watch } from "vue";
import { showToast } from "./useToast.js";

/**
 * WebSocket 实时行情订阅 composable
 * 
 * 连接流程:
 *  1. 调用 useQuote() 创建行情订阅器
 *  2. 调用 subscribe(codes) 订阅标的
 *  3. 通过 quotes ref 获取实时行情数据
 *  4. 组件销毁时自动断开连接
 * 
 * 使用示例:
 * const { quotes, subscribe, unsubscribe, connected } = useQuote();
 * await subscribe(["sh.600000", "sz.000001"]);
 * 
 * 行情数据格式:
 * {
 *   type: "quote",
 *   code: "sh.600000",
 *   name: "浦发银行",
 *   price: 10.55,
 *   open: 10.50,
 *   high: 10.60,
 *   low: 10.45,
 *   pre_close: 10.48,
 *   change: 0.07,
 *   change_pct: 0.67,
 *   volume: 1250000,
 *   amount: 13187500,
 *   bid1: 10.54,
 *   ask1: 10.56,
 *   bid1_vol: 500,
 *   ask1_vol: 800,
 *   timestamp: "2024-01-15T10:30:00.000Z",
 *   source: "sina"
 * }
 */

const RECONNECT_DELAY = 3000;
const PING_INTERVAL = 15000;

export function useQuote() {
  const ws = ref(null);
  const connected = ref(false);
  const connecting = ref(false);
  const quotes = ref({}); // { [code]: quote }
  const subscribedCodes = ref(new Set());
  
  let reconnectTimer = null;
  let pingTimer = null;

  /**
   * 获取 WebSocket 连接 URL
   */
  function getWsUrl() {
    const raw = import.meta.env.VITE_API_BASE;
    const base = typeof raw === "string" && raw.trim() ? raw.trim() : window.location.origin;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = base.replace(/^https?:\/\//, "");
    return `${protocol}//${host}/ws/quotes`;
  }

  /**
   * 发送消息到服务端
   */
  function sendMessage(action, codes = []) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket not connected, cannot send:", action);
      return;
    }
    try {
      ws.value.send(JSON.stringify({ action, codes }));
    } catch (e) {
      console.error("WebSocket send error:", e);
    }
  }

  /**
   * 处理收到的消息
   */
  function handleMessage(event) {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "quote") {
        quotes.value = {
          ...quotes.value,
          [data.code]: { ...data },
        };
      } else if (data.type === "subscribed") {
        data.codes.forEach(code => subscribedCodes.value.add(code));
      } else if (data.type === "unsubscribed") {
        data.codes.forEach(code => subscribedCodes.value.delete(code));
      } else if (data.type === "pong") {
        // 心跳响应，无需处理
      } else if (data.type === "error") {
        showToast(`行情错误: ${data.message}`, { type: "error" });
      }
    } catch (e) {
      console.error("WebSocket message parse error:", e);
    }
  }

  /**
   * 启动心跳
   */
  function startPing() {
    stopPing();
    pingTimer = setInterval(() => {
      sendMessage("ping");
    }, PING_INTERVAL);
  }

  /**
   * 停止心跳
   */
  function stopPing() {
    if (pingTimer) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
  }

  /**
   * 连接 WebSocket
   */
  async function connect() {
    if (connected.value || connecting.value) return;
    
    connecting.value = true;
    
    try {
      const url = getWsUrl();
      ws.value = new WebSocket(url);
      
      ws.value.onopen = () => {
        connected.value = true;
        connecting.value = false;
        startPing();
        
        // 重新订阅之前订阅的标的
        if (subscribedCodes.value.size > 0) {
          sendMessage("subscribe", Array.from(subscribedCodes.value));
        }
        
        console.log("WebSocket connected");
      };
      
      ws.value.onmessage = handleMessage;
      
      ws.value.onerror = (error) => {
        console.error("WebSocket error:", error);
        showToast("行情连接异常", { type: "error" });
      };
      
      ws.value.onclose = () => {
        connected.value = false;
        connecting.value = false;
        stopPing();
        console.log("WebSocket disconnected");
        
        // 自动重连
        if (subscribedCodes.value.size > 0) {
          reconnectTimer = setTimeout(() => {
            connect();
          }, RECONNECT_DELAY);
        }
      };
    } catch (e) {
      connecting.value = false;
      console.error("WebSocket connect error:", e);
      showToast("无法连接行情服务器", { type: "error" });
    }
  }

  /**
   * 断开 WebSocket 连接
   */
  function disconnect() {
    stopPing();
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    
    if (ws.value) {
      try {
        ws.value.close();
      } catch (e) {
        console.error("WebSocket close error:", e);
      }
      ws.value = null;
    }
    
    connected.value = false;
    connecting.value = false;
  }

  /**
   * 订阅标的
   * @param {string|string[]} codes - 标的代码，可以是单个字符串或字符串数组
   */
  async function subscribe(codes) {
    const codeList = Array.isArray(codes) ? codes : [codes];
    const validCodes = codeList.filter(c => c && typeof c === "string");
    
    if (validCodes.length === 0) return;
    
    if (!connected.value && !connecting.value) {
      await connect();
    }
    
    // 等待连接建立
    if (!connected.value) {
      await new Promise(resolve => {
        const check = setInterval(() => {
          if (connected.value) {
            clearInterval(check);
            resolve();
          }
        }, 50);
        setTimeout(() => {
          clearInterval(check);
          resolve();
        }, 5000);
      });
    }
    
    sendMessage("subscribe", validCodes);
  }

  /**
   * 取消订阅标的
   * @param {string|string[]} codes - 标的代码，可以是单个字符串或字符串数组
   */
  function unsubscribe(codes) {
    const codeList = Array.isArray(codes) ? codes : [codes];
    const validCodes = codeList.filter(c => c && typeof c === "string");
    
    if (validCodes.length === 0) return;
    
    sendMessage("unsubscribe", validCodes);
    
    // 从本地缓存中移除
    validCodes.forEach(code => {
      delete quotes.value[code];
    });
  }

  /**
   * 获取指定标的的行情
   * @param {string} code - 标的代码
   * @returns {object|null} - 行情数据
   */
  function getQuote(code) {
    return quotes.value[code] || null;
  }

  /**
   * 清空所有订阅
   */
  function clearAll() {
    unsubscribe(Array.from(subscribedCodes.value));
    quotes.value = {};
    subscribedCodes.value.clear();
    disconnect();
  }

  /**
   * 组件销毁时自动清理
   */
  onUnmounted(() => {
    clearAll();
  });

  return {
    ws,
    connected,
    connecting,
    quotes,
    subscribedCodes,
    subscribe,
    unsubscribe,
    getQuote,
    clearAll,
    connect,
    disconnect,
  };
}

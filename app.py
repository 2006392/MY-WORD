# -*- coding: utf-8 -*-
# ============================================================
#  银行智能助手「小智」2.0 比赛增强版
#  运行方法: streamlit run app.py --server.port 8501
#  安装依赖: pip install streamlit openai
#  覆盖赛道: 智能业务办理 / 风控反诈 / 适老关怀 / 数据可视化 / 透明可信
# ============================================================
import json
import os
import streamlit as st
import pandas as pd
from openai import OpenAI

# ========== 1. 配置区（只需要改 api_key 这一行） ==========
client = OpenAI(
            api_key=os.environ.get("ZHIPU_API_KEY", ""),
    base_url="https://open.bigmodel.cn/api/paas/v4/"
)
MODEL = "glm-4-flash"      # 智谱免费模型
BIG_AMOUNT = 5000          # 大额转账二次确认阈值（元）

FRAUD_WORDS = ["安全账户", "公检法", "洗钱", "刷单", "屏幕共享", "验证码",
               "中奖", "冻结", "解冻费", "保证金", "杀猪盘", "网警",
               "冒充", "兼职点赞", "转账到指定账户", "汇款手续费"]

# ========== 2. 模拟银行系统（比赛演示数据） ==========
ACCOUNTS = {
    "张三": {"余额": 5000.0,  "手机号": "13800000001", "等级": "普通客户"},
    "李四": {"余额": 300.0,   "手机号": "13800000002", "等级": "普通客户"},
    "王五": {"余额": 12000.0, "手机号": "13800000003", "等级": "黄金客户"},
}
TRANSACTIONS = [
    {"商户": "美团外卖", "金额": 35.5,  "分类": "餐饮", "日期": "2026-10-01"},
    {"商户": "瑞幸咖啡", "金额": 19.9,  "分类": "餐饮", "日期": "2026-10-02"},
    {"商户": "滴滴出行", "金额": 22.0,  "分类": "交通", "日期": "2026-10-03"},
    {"商户": "地铁充值", "金额": 50.0,  "分类": "交通", "日期": "2026-10-05"},
    {"商户": "腾讯视频", "金额": 25.0,  "分类": "订阅", "日期": "2026-10-06"},
    {"商户": "京东购物", "金额": 199.0, "分类": "购物", "日期": "2026-10-07"},
    {"商户": "肯德基",   "金额": 45.0,  "分类": "餐饮", "日期": "2026-10-09"},
    {"商户": "拼多多",   "金额": 88.0,  "分类": "购物", "日期": "2026-10-12"},
    {"商户": "电影票",   "金额": 39.9,  "分类": "娱乐", "日期": "2026-10-14"},
    {"商户": "药房购药", "金额": 66.8,  "分类": "医疗", "日期": "2026-10-15"},
]

# ========== 3. 工具函数（Agent 的手脚） ==========
def query_balance(name):
    if name not in ACCOUNTS:
        return {"status": "fail", "msg": f"没有找到客户{name}"}
    return {"status": "ok", "客户": name, "余额": ACCOUNTS[name]["余额"]}

def do_transfer(from_name, to_name, amount):
    ACCOUNTS[from_name]["余额"] -= amount
    ACCOUNTS[to_name]["余额"] += amount
    TRANSACTIONS.append({"商户": f"转账给{to_name}", "金额": amount,
                         "分类": "转账", "日期": "2026-10-27"})
    st.session_state["tx_count"] += 1
    return {"status": "ok",
            "msg": f"转账成功：{from_name} → {to_name}，金额{amount}元",
            "新余额": ACCOUNTS[from_name]["余额"]}

def transfer_money(from_name, to_name, amount):
    amount = float(amount)
    if from_name not in ACCOUNTS:
        return {"status": "fail", "msg": "转出账户不存在"}
    if to_name not in ACCOUNTS:
        return {"status": "fail", "msg": "收款账户不存在"}
    if from_name == to_name:
        return {"status": "fail", "msg": "不能转账给自己"}
    if amount <= 0:
        return {"status": "fail", "msg": "金额必须大于0"}
    if amount > ACCOUNTS[from_name]["余额"]:
        return {"status": "fail",
                "msg": f"余额不足，当前余额{ACCOUNTS[from_name]['余额']}元"}
    if amount >= BIG_AMOUNT:
        st.session_state["pending"] = {"from": from_name, "to": to_name, "amount": amount}
        return {"status": "need_confirm",
                "msg": f"金额{amount}元达到大额标准（{BIG_AMOUNT}元），已触发风控，需用户回复'确认'后执行"}
    return do_transfer(from_name, to_name, amount)

def get_transactions(limit=10):
    return {"status": "ok", "最近交易": TRANSACTIONS[-int(limit):]}

def analyze_spending():
    df = pd.DataFrame(TRANSACTIONS)
    g = df.groupby("分类")["金额"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    rows = [{"分类": i, "总金额": float(r["sum"]), "笔数": int(r["count"])} for i, r in g.iterrows()]
    return {"status": "ok", "分类统计": rows, "总支出": float(df["金额"].sum())}

TOOLS = [
    {"type": "function", "function": {"name": "query_balance",
        "description": "查询指定客户的银行账户余额",
        "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "客户姓名"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {"name": "transfer_money",
        "description": "从一名客户转账给另一名客户，金额达到5000元会触发二次确认",
        "parameters": {"type": "object", "properties": {
            "from_name": {"type": "string", "description": "转出客户姓名"},
            "to_name": {"type": "string", "description": "收款客户姓名"},
            "amount": {"type": "number", "description": "金额，单位元"}},
            "required": ["from_name", "to_name", "amount"]}}},
    {"type": "function", "function": {"name": "get_transactions",
        "description": "查询最近的交易明细",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "description": "条数，默认10"}}}}},
    {"type": "function", "function": {"name": "analyze_spending",
        "description": "统计消费分类汇总，用于账单分析和理财建议",
        "parameters": {"type": "object", "properties": {}}}},
]
TOOL_MAP = {"query_balance": query_balance, "transfer_money": transfer_money,
            "get_transactions": get_transactions, "analyze_spending": analyze_spending}

# ========== 4. AI 大脑 ==========
BASE_SYSTEM = ("你是银行智能客服助手'小智'，可以调用工具帮用户办理业务："
               "查余额(query_balance)、转账(transfer_money)、查交易明细(get_transactions)、"
               "消费分析(analyze_spending)。规则：1.转账前先确认收款人和金额；"
               "2.工具返回need_confirm时，向用户说明大额风控并请其回复'确认'；"
               "3.用户只说查余额没说姓名时，先询问是哪位客户；"
               "4.回答简洁友好，金额用元表示；5.账单分析要给出实用建议。")

def agent_reply(history, sys_extra="", elder=False):
    log = []
    sys_prompt = BASE_SYSTEM + sys_extra
    if elder:
        sys_prompt += ("\n[适老模式] 当前的用户是老年客户：请全程使用通俗大白话，"
                       "不打专业术语；金额、收款人等关键信息重复说两遍；语气放慢、多鼓励。")
    messages = [{"role": "system", "content": sys_prompt}] + history[-12:]
    for _ in range(5):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": t.id, "type": "function",
                 "function": {"name": t.function.name, "arguments": t.function.arguments}}
                for t in msg.tool_calls]})
            for t in msg.tool_calls:
                try:
                    args = json.loads(t.function.arguments or "{}")
                except Exception:
                    args = {}
                log.append(f"🛠 调用工具：{t.function.name}({args})")
                try:
                    result = TOOL_MAP[t.function.name](**args)
                except TypeError:
                    result = TOOL_MAP[t.function.name]()
                log.append(f"📋 工具返回：{json.dumps(result, ensure_ascii=False)}")
                messages.append({"role": "tool", "tool_call_id": t.id,
                                 "content": json.dumps(result, ensure_ascii=False)})
            continue
        reply = msg.content or "（AI 未返回内容，请重试）"
        log.append("💬 AI 生成最终回复")
        return reply, log
    return "抱歉，业务处理超时，请重新描述您的需求。", log

# ========== 5. 页面初始化 ==========
st.set_page_config(page_title="银行AI助手2.0", page_icon="🏦", layout="wide")

if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.display = []
    st.session_state.pending = None
    st.session_state.tx_count = 0
    st.session_state.fraud_count = 0

elder = st.sidebar.toggle("🍯 适老关怀模式", value=False,
                          help="放大字体，AI切换为通俗话术")
if elder:
    st.markdown("""<style>
    [data-testid="stMarkdownContainer"] p {font-size:1.35rem !important; line-height:1.8 !important;}
    </style>""", unsafe_allow_html=True)

# ---------- 侧边栏：实时仪表盘 ----------
with st.sidebar:
    st.header("📊 风控与运营仪表盘")
    c1, c2, c3 = st.columns(3)
    c1.metric("在管客户", len(ACCOUNTS))
    c2.metric("已办业务", st.session_state.tx_count)
    c3.metric("风险拦截", st.session_state.fraud_count)

    st.subheader("客户账户")
    st.dataframe(pd.DataFrame(
        [{"客户": k, "余额": v["余额"], "等级": v["等级"]} for k, v in ACCOUNTS.items()]),
        use_container_width=True, hide_index=True)

    st.subheader("本月消费结构")
    df = pd.DataFrame(TRANSACTIONS)
    st.bar_chart(df.groupby("分类")["金额"].sum(), height=200)
    st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("🔄 重置对话", use_container_width=True):
        st.session_state.history = []
        st.session_state.display = []
        st.session_state.pending = None
        st.rerun()

# ---------- 主区标题 ----------
st.title("🏦 银行 AI 智能助手 · 小智 2.0")
st.caption("智能业务办理 · 大额风控 · 反诈守护 · 适老关怀 · 全程透明可解释")

# ---------- 处理消息（先处理，后渲染，保证即时显示） ----------
def handle_user(text):
    st.session_state.history.append({"role": "user", "content": text})
    st.session_state.display.append({"role": "user", "content": text, "avatar": "🧑‍💼"})

    # (1) 本地反诈引擎：关键词命中 → 红色警报
    hits = [w for w in FRAUD_WORDS if w in text]
    alert = "、".join(hits) if hits else None
    if hits:
        st.session_state.fraud_count += 1

    # (2) 大额转账二次确认：用户回复"确认" → 立即执行
    pending = st.session_state.pending
    if pending and any(w in text for w in ["确认", "确定", "同意", "是的", "可以"]):
        info = st.session_state.pop("pending")
        result = do_transfer(info["from"], info["to"], info["amount"])
        reply = (f"✅ 二次确认通过，已执行转账。\n\n{result['msg']}。\n\n"
                 f"{info['from']} 当前余额：{result['新余额']} 元")
        st.session_state.history.append({"role": "assistant", "content": reply})
        st.session_state.display.append({"role": "assistant", "content": reply,
                                         "avatar": "🏦", "alert": alert})
        return

    # (3) 交给 AI 大脑（命中诈骗词则注入风控警报）
    sys_extra = (f"\n[风控警报] 用户消息命中疑似诈骗关键词：{alert}。"
                 f"请先以反诈专员身份郑重提醒风险、核实情况，再处理其他请求。" if alert else "")
    reply, log = agent_reply(st.session_state.history, sys_extra, elder)
    st.session_state.history.append({"role": "assistant", "content": reply})
    st.session_state.display.append({"role": "assistant", "content": reply,
                                     "avatar": "🏦", "log": log, "alert": alert})

quick_items = ["💰 查我的余额", "💸 给王五转20000", "📊 分析我的账单", "🚨 反诈演练"]
cols = st.columns(4)
clicked = None
for c, q in zip(cols, quick_items):
    if c.button(q, use_container_width=True):
        clicked = {"💰 查我的余额": "查一下张三的余额",
                   "💸 给王五转20000": "给王五转20000元",
                   "📊 分析我的账单": "分析一下张三这个月的消费账单",
                   "🚨 反诈演练": "刚才接到电话，对方自称公检法，让我把钱转到安全账户"}[q]
if clicked:
    handle_user(clicked)

prompt = st.chat_input("请输入需求，例如：给李四转100元 / 查余额 / 分析账单")
if prompt:
    handle_user(prompt)

# ---------- 渲染聊天记录 ----------
for m in st.session_state.display:
    with st.chat_message(m["role"], avatar=m.get("avatar", "🏦")):
        if m.get("alert"):
            st.error(f"🚨 风控警报：检测到疑似诈骗关键词（{m['alert']}）！"
                     f"公安机关不会电话要求转账，切勿向陌生账户汇款！")
        st.markdown(m["content"])
        if m.get("log"):
            with st.expander("🔍 查看 AI 的调用过程（透明可解释）"):
                st.write("\n".join(m["log"]))

st.caption("⚠️ 本系统为比赛演示原型，账户与交易数据均为模拟数据，不涉及真实资金；"

           "AI 建议仅供参考，不构成投资建议。")

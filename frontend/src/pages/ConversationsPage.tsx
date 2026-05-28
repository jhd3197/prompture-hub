import { useEffect, useState } from "react";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { Modal } from "../components/Modal";
import { useToast } from "../components/Toast";
import {
  IconAlert, IconBot, IconCog, IconMessages, IconRefresh, IconTrash, IconUser,
} from "../icons";
import type { ConversationDetail, ConversationSummary } from "../types";

function timeAgo(iso: string): string {
  const d = new Date(iso);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  if (sec < 604800) return `${Math.floor(sec / 86400)}d ago`;
  return d.toLocaleDateString();
}

function roleIcon(role: string) {
  if (role === "user") return <IconUser />;
  if (role === "assistant") return <IconBot />;
  if (role === "system") return <IconCog />;
  return <IconMessages />;
}

function roleColor(role: string): string {
  if (role === "user") return "var(--info)";
  if (role === "assistant") return "var(--accent-strong)";
  if (role === "system") return "var(--vault)";
  return "var(--text-3)";
}

function MessageBubble({ msg }: { msg: ConversationDetail["messages"][number] }) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div
        className="card-head"
        style={{
          padding: "10px 14px",
          background: "var(--surface-2)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div className="row" style={{ gap: 8 }}>
          <span style={{ color: roleColor(msg.role), display: "inline-flex" }}>
            <span style={{ width: 14, height: 14 }}>{roleIcon(msg.role)}</span>
          </span>
          <span className="strong" style={{ fontWeight: 700, fontSize: 12.5, textTransform: "capitalize" }}>
            {msg.role}
          </span>
        </div>
        <span className="sub" style={{ marginLeft: "auto", fontSize: 11.5 }}>
          {msg.total_tokens > 0 && (
            <>
              <span className="mono tnum">{msg.total_tokens.toLocaleString()}</span> tok
              {msg.cost_usd > 0 && (
                <>
                  {" "}· <span className="mono tnum">${msg.cost_usd.toFixed(5)}</span>
                </>
              )}{" "}·{" "}
            </>
          )}
          {timeAgo(msg.created_at)}
        </span>
      </div>
      <div
        style={{
          padding: "14px 16px",
          fontSize: 13.5,
          lineHeight: 1.55,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          color: "var(--text)",
        }}
      >
        {msg.content || <span className="faint">(empty)</span>}
      </div>
    </div>
  );
}

function ConversationList({
  conversations, selectedId, onSelect,
}: {
  conversations: ConversationSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (conversations.length === 0) {
    return (
      <EmptyState icon={<IconMessages />} title="No conversations yet">
        Apps create conversations by calling <code className="mono">/v1/conversations</code>.
        Once one of your hub keys persists a session, it'll show up here.
      </EmptyState>
    );
  }
  return (
    <div className="keylist">
      {conversations.map(c => (
        <button
          key={c.id}
          onClick={() => onSelect(c.id)}
          className="keylist-item"
          style={{
            border: "none",
            background: c.id === selectedId ? "var(--surface-2)" : "transparent",
            width: "100%",
            textAlign: "left",
            padding: "12px 14px",
            cursor: "pointer",
            borderLeft: c.id === selectedId ? "2px solid var(--accent)" : "2px solid transparent",
          }}
        >
          <span style={{ color: "var(--accent-strong)", display: "inline-flex" }}>
            <span style={{ width: 16, height: 16 }}><IconMessages /></span>
          </span>
          <div className="grow" style={{ minWidth: 0 }}>
            <div
              className="strong"
              style={{
                fontWeight: 600, fontSize: 13,
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}
            >
              {c.title || <span className="faint mono">{c.id}</span>}
            </div>
            <div className="mono faint" style={{ fontSize: 11, marginTop: 1 }}>
              {c.message_count} msg{c.message_count !== 1 ? "s" : ""}
              {c.model && (
                <>
                  {" "}· {c.model}
                </>
              )}
            </div>
          </div>
          <div className="right">
            <div className="faint" style={{ fontSize: 11 }}>{timeAgo(c.updated_at)}</div>
          </div>
        </button>
      ))}
    </div>
  );
}

function ConversationDetailView({
  detail, onDelete,
}: {
  detail: ConversationDetail;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="card">
      <div className="card-head">
        <div className="grow" style={{ minWidth: 0 }}>
          <h3 style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {detail.title || <span className="mono faint">{detail.id}</span>}
          </h3>
          <div className="sub" style={{ display: "block", marginTop: 2 }}>
            {detail.model && <><span className="mono">{detail.model}</span> · </>}
            key #{detail.key_id} · created {timeAgo(detail.created_at)}
          </div>
        </div>
        <button
          className="btn btn-sm btn-danger"
          onClick={() => setConfirming(true)}
          aria-label="Delete conversation"
        >
          <IconTrash />Delete
        </button>
      </div>

      <div
        className="stat-grid"
        style={{
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 1,
          background: "var(--border)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div className="stat" style={{ borderRadius: 0, border: "none", boxShadow: "none" }}>
          <div className="stat-label">Messages</div>
          <div className="stat-value tnum" style={{ fontSize: 22 }}>
            {detail.totals.message_count}
          </div>
        </div>
        <div className="stat" style={{ borderRadius: 0, border: "none", boxShadow: "none" }}>
          <div className="stat-label">Total tokens</div>
          <div className="stat-value tnum" style={{ fontSize: 22 }}>
            {detail.totals.total_tokens.toLocaleString()}
          </div>
          <div className="stat-meta" style={{ fontSize: 11 }}>
            {detail.totals.prompt_tokens.toLocaleString()} in ·{" "}
            {detail.totals.completion_tokens.toLocaleString()} out
          </div>
        </div>
        <div className="stat" style={{ borderRadius: 0, border: "none", boxShadow: "none" }}>
          <div className="stat-label">Cost</div>
          <div className="stat-value tnum" style={{ fontSize: 22 }}>
            ${detail.totals.cost_usd.toFixed(4)}
          </div>
        </div>
      </div>

      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        {detail.messages.length === 0 ? (
          <EmptyState icon={<IconMessages />} title="No messages yet">
            This conversation was created but no messages were appended.
          </EmptyState>
        ) : (
          detail.messages.map(m => <MessageBubble key={m.id} msg={m} />)
        )}
      </div>

      {confirming && (
        <Modal
          title={`Delete this conversation?`}
          desc="The message history will be permanently removed. This does not delete or revoke the hub key that created it."
          onClose={() => setConfirming(false)}
          footer={<>
            <button className="btn btn-ghost" onClick={() => setConfirming(false)}>Keep it</button>
            <button className="btn btn-danger" onClick={() => { setConfirming(false); onDelete(); }}>
              <IconTrash />Delete
            </button>
          </>}
        >
          <div className="row" style={{
            gap: 10, padding: "12px 14px",
            background: "var(--danger-soft)", borderRadius: "var(--r-md)",
          }}>
            <span className="kdot dead"></span>
            <div>
              <div className="mono strong" style={{ fontWeight: 600 }}>
                {detail.title || detail.id}
              </div>
              <div className="faint" style={{ fontSize: 12 }}>
                {detail.totals.message_count} message{detail.totals.message_count !== 1 ? "s" : ""} ·{" "}
                {detail.totals.total_tokens.toLocaleString()} tokens
              </div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

export function ConversationsPage() {
  const [list, setList] = useState<ConversationSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const toast = useToast();

  const refreshList = async () => {
    setLoadingList(true);
    try {
      const items = await api.listConversations();
      setList(items);
      setListError(null);
      if (!selectedId && items.length > 0) {
        setSelectedId(items[0].id);
      }
    } catch (e) {
      setListError(String(e));
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => { refreshList(); }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setLoadingDetail(true);
    setDetailError(null);
    api.getConversation(selectedId)
      .then(d => { setDetail(d); setLoadingDetail(false); })
      .catch(e => {
        setDetailError(String(e));
        setLoadingDetail(false);
      });
  }, [selectedId]);

  const handleDelete = async () => {
    if (!selectedId) return;
    try {
      await api.deleteConversation(selectedId);
      toast("Conversation deleted");
      setSelectedId(null);
      setDetail(null);
      await refreshList();
    } catch (e) {
      toast(`Couldn't delete: ${e}`);
    }
  };

  return (
    <div className="container">
      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Conversations</h1>
          <p className="page-sub">
            Resumable chat sessions persisted by your apps via{" "}
            <code className="mono">/v1/conversations</code>. The hub stores every turn
            so a later request can pick up where it left off.
          </p>
        </div>
        <button className="btn" onClick={refreshList}>
          <IconRefresh style={{ width: 14, height: 14 }} />Refresh
        </button>
      </div>

      {listError && (
        <div className="discovery-fail mb16" role="alert" style={{
          borderRadius: "var(--r-md)",
          border: "1px solid var(--danger)",
          background: "var(--danger-soft)",
        }}>
          <IconAlert />
          <span className="mono">{listError}</span>
        </div>
      )}

      <div className="grid-dash" style={{ alignItems: "start" }}>
        <div className="card" style={{ padding: 0 }}>
          <div className="card-head">
            <h3>Sessions</h3>
            <span className="sub">{list.length} total</span>
          </div>
          {loadingList ? (
            <div className="empty"><p>Loading…</p></div>
          ) : (
            <ConversationList
              conversations={list}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          )}
        </div>

        <div>
          {loadingDetail ? (
            <div className="card card-pad"><p className="faint">Loading messages…</p></div>
          ) : detailError ? (
            <div className="card card-pad">
              <EmptyState icon={<IconAlert />} title="Couldn't load conversation">
                {detailError}
              </EmptyState>
            </div>
          ) : detail ? (
            <ConversationDetailView detail={detail} onDelete={handleDelete} />
          ) : (
            <div className="card card-pad">
              <EmptyState icon={<IconMessages />} title="Pick a session">
                Select a conversation from the left to view its message history,
                token totals and cost.
              </EmptyState>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

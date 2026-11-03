import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Modal } from "../components/Modal";
import { PageHead } from "../components/PageHead";
import { Skel, SkelRows } from "../components/Skeleton";
import { useToast } from "../components/Toast";
import { CopyId } from "../components/CopyId";
import { IconBot, IconCog, IconMessages, IconRefresh, IconTrash, IconUser } from "../icons";
import { publishSessions } from "../util/catalog";
import { errText, int, plural, timeAgo, usd } from "../util/format";
import { useAsync } from "../util/hooks";
import type { ConversationDetail } from "../types";

function roleIcon(role: string) {
  if (role === "user") return <IconUser />;
  if (role === "assistant") return <IconBot />;
  if (role === "system") return <IconCog />;
  return <IconMessages />;
}

function Message({ msg, peak }: { msg: ConversationDetail["messages"][number]; peak: number }) {
  return (
    <article className={`msg msg-${msg.role}`}>
      <header className="msg-head">
        <span className="msg-role">{roleIcon(msg.role)}{msg.role}</span>
        {msg.total_tokens > 0 && (
          <span className="msg-cost" title={`${int(msg.prompt_tokens)} in, ${int(msg.completion_tokens)} out`}>
            <span className="msg-bar" aria-hidden="true"><i style={{ ["--p" as string]: msg.total_tokens / peak }} /></span>
            <span className="mono tnum">{int(msg.total_tokens)} tok</span>
            {msg.cost_usd > 0 && <span className="mono tnum">{usd(msg.cost_usd, 5)}</span>}
          </span>
        )}
        <time className="faint" dateTime={msg.created_at}>{timeAgo(msg.created_at)}</time>
      </header>
      <div className="msg-body">{msg.content || <span className="faint">(empty)</span>}</div>
    </article>
  );
}

function DetailView({ detail, onDelete }: { detail: ConversationDetail; onDelete: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const peak = Math.max(...detail.messages.map(m => m.total_tokens), 1);
  return (
    <section className="panel" aria-labelledby="sess-title">
      <div className="panel-head" style={{ alignItems: "flex-start" }}>
        <div className="grow">
          <h2 id="sess-title" className="truncate" style={{ fontSize: "var(--t-md)" }}>{detail.title || detail.id}</h2>
          <div className="sub" style={{ marginTop: 2 }}>
            {detail.model ?? "no model"} / key #{detail.key_id} / created {timeAgo(detail.created_at)}
          </div>
        </div>
        <CopyId value={detail.id} display="copy id" label="session id" />
        <button type="button" className="btn btn-sm btn-danger" onClick={() => setConfirming(true)} aria-label="Delete conversation"><IconTrash />Delete</button>
      </div>

      <div className="readouts" style={{ ["--cols" as string]: "repeat(3, minmax(0, 1fr))", border: 0, borderRadius: 0, borderBottom: "1px solid var(--line)" }}>
        <div className="readout" style={{ padding: "14px 16px" }}>
          <span className="caption">Messages</span>
          <div className="readout-value" style={{ fontSize: 26 }}>{detail.totals.message_count}</div>
        </div>
        <div className="readout" style={{ padding: "14px 16px" }}>
          <span className="caption">Tokens</span>
          <div className="readout-value" style={{ fontSize: 26 }}>{int(detail.totals.total_tokens)}</div>
          <div className="readout-meta">{int(detail.totals.prompt_tokens)} in, {int(detail.totals.completion_tokens)} out</div>
        </div>
        <div className="readout" style={{ padding: "14px 16px" }}>
          <span className="caption">Cost</span>
          <div className="readout-value" style={{ fontSize: 26 }}>{usd(detail.totals.cost_usd)}</div>
        </div>
      </div>

      <div className="msgs">
        {detail.messages.length === 0 ? (
          <EmptyState icon={<IconMessages />} title="No messages yet">This conversation exists but no turns were appended to it.</EmptyState>
        ) : detail.messages.map(m => <Message key={m.id} msg={m} peak={peak} />)}
      </div>

      {confirming && (
        <Modal
          title="Delete this conversation?"
          desc="The message history is removed permanently. The hub key that created it is not touched."
          onClose={() => setConfirming(false)}
          footer={<>
            <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>Keep it</button>
            <button type="button" className="btn btn-danger" onClick={() => { setConfirming(false); onDelete(); }}><IconTrash />Delete</button>
          </>}
        >
          <div className="notice bad">
            <span className="kdot dead" style={{ marginTop: 6 }} />
            <div>
              <div className="mono strong" style={{ fontWeight: 600 }}>{detail.title || detail.id}</div>
              <div className="faint" style={{ fontSize: 12 }}>{plural(detail.totals.message_count, "message")}, {int(detail.totals.total_tokens)} tokens</div>
            </div>
          </div>
        </Modal>
      )}
    </section>
  );
}

export function ConversationsPage() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const list = useAsync(() => api.listConversations(), []);
  const wanted = params.get("s");
  const [selected, setSelected] = useState<string | null>(wanted);
  const detailRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (list.data) publishSessions(list.data); }, [list.data]);
  useEffect(() => { if (wanted) setSelected(wanted); }, [wanted]);
  // Default to the newest session once the list arrives.
  useEffect(() => {
    if (list.data && list.data.length > 0 && (!selected || !list.data.some(c => c.id === selected))) setSelected(list.data[0].id);
  }, [list.data, selected]);

  const detail = useAsync(async () => (selected ? api.getConversation(selected) : null), [selected]);

  const pick = (id: string) => {
    setSelected(id);
    if (params.get("s")) setParams({}, { replace: true });
    if (window.innerWidth < 1000) setTimeout(() => detailRef.current?.scrollIntoView({ block: "start" }), 0);
  };

  const remove = async () => {
    if (!selected) return;
    try {
      await api.deleteConversation(selected);
      toast("Conversation deleted");
      setSelected(null);
      list.reload();
    } catch (e) {
      toast(`Couldn't delete: ${errText(e)}`);
    }
  };

  const items = list.data ?? [];

  return (
    <div className="container">
      <PageHead title="Sessions" docTitle="Sessions" sub={<>Resumable chats your apps persist through <code className="mono">/v1/conversations</code>. The hub stores every turn so a later request can pick up where it left off.</>}>
        <button type="button" className="btn" onClick={list.reload}><IconRefresh />Refresh</button>
      </PageHead>

      <div className="cols sessions-cols">
        <section className="panel" aria-labelledby="sess-list">
          <div className="panel-head"><h2 id="sess-list">All sessions</h2><span className="sub">{list.data ? `${items.length} total` : "loading"}</span></div>
          {list.error && !list.data ? (
            <ErrorState title="Couldn't load sessions" error={list.error} onRetry={list.reload} />
          ) : !list.data ? (
            <SkelRows rows={6} label="Loading sessions" />
          ) : items.length === 0 ? (
            <EmptyState icon={<IconMessages />} title="No sessions yet">
              Apps create a session by calling <code className="mono">/v1/conversations</code>. Once one of your hub keys saves a chat, it is listed here with its cost.
            </EmptyState>
          ) : (
            <ul className="sess-list">
              {items.map(c => (
                <li key={c.id}>
                  <button type="button" className={`sess${c.id === selected ? " on" : ""}`} aria-current={c.id === selected ? "true" : undefined} onClick={() => pick(c.id)}>
                    <span className="sess-main">
                      <span className="sess-title truncate">{c.title || c.id}</span>
                      <span className="sess-sub mono truncate">{plural(c.message_count, "msg")}{c.model && <> / {c.model}</>}</span>
                    </span>
                    <span className="faint sess-when">{timeAgo(c.updated_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div ref={detailRef} style={{ scrollMarginTop: "calc(var(--bar-h) + 12px)" }}>
          {detail.error ? (
            <div className="panel"><ErrorState title="Couldn't load this session" error={detail.error} onRetry={detail.reload} /></div>
          ) : detail.loading && !detail.data ? (
            <div className="panel panel-pad" aria-busy="true" role="status" aria-label="Loading messages">
              <Skel w="40%" h={16} /><div style={{ height: 16 }} /><Skel h={64} /><div style={{ height: 12 }} /><Skel h={64} />
            </div>
          ) : detail.data ? (
            <DetailView key={detail.data.id} detail={detail.data} onDelete={remove} />
          ) : list.data ? (
            <div className="panel"><EmptyState icon={<IconMessages />} title="Pick a session">Select a conversation to read its turns, token totals and cost.</EmptyState></div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

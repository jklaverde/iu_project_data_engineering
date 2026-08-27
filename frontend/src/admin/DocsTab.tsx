import { useEffect, useState } from "react";
import { marked } from "marked";
import { fetchAdminDoc, fetchAdminDocs } from "../api";
import type { AdminDocSummary } from "../types";

export default function DocsTab() {
  const [docs, setDocs] = useState<AdminDocSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [title, setTitle] = useState<string>("");
  const [html, setHtml] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAdminDocs()
      .then((res) => {
        if (cancelled) return;
        setDocs(res.docs);
        if (res.docs.length > 0) setActiveId(res.docs[0].id);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load the document list.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    setError(null);
    fetchAdminDoc(activeId)
      .then((doc) => {
        if (cancelled) return;
        setTitle(doc.title);
        // Content is the project's own bundled .md files (backend/Dockerfile
        // COPYs them in at build time) - not user-supplied - so rendering
        // marked's output directly is safe here.
        setHtml(marked.parse(doc.content, { async: false }) as string);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load this document.");
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  return (
    <div className="body">
      <nav className="stepper docs-nav">
        {docs.map((d) => (
          <button
            key={d.id}
            className={d.id === activeId ? "step-active" : ""}
            onClick={() => setActiveId(d.id)}
          >
            {d.title}
          </button>
        ))}
      </nav>
      <main>
        <div className="step docs-content">
          {error && <p className="step-error">{error}</p>}
          {!error && !html && <p className="waiting">Loading {title || "document"}...</p>}
          {!error && html && <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />}
        </div>
      </main>
    </div>
  );
}

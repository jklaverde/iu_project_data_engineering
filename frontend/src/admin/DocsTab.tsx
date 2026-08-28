const DOCS_SITE_URL = "/api/admin/docs-site/index.html";

export default function DocsTab() {
  return (
    <div className="step">
      <h3>Docs</h3>
      <p className="waiting">
        The project's own documentation site — architecture, deployment, operations &amp;
        troubleshooting, and a file-by-file reference. The same pages a developer opens directly
        from the repo (<code>docs/index.html</code>, no server needed), served here so they're
        reachable from inside the running app too.
      </p>
      <div className="docs-toolbar">
        <a className="btn btn-ghost" href={DOCS_SITE_URL} target="_blank" rel="noreferrer">
          Open in new tab ↗
        </a>
      </div>
      <div className="docs-frame-wrap">
        <iframe className="docs-frame" src={DOCS_SITE_URL} title="Documentation" />
      </div>
    </div>
  );
}

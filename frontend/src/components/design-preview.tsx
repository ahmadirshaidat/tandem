import { Flag, Link2, MessageSquare, Sparkles } from "lucide-react";

/** Decorative example from the supplied canvas, outside the live workspace. */
export function ProposalPreview() {
  return (
    <figure className="proposal-preview">
      <figcaption className="text-small text-muted">Product preview</figcaption>
      <div className="card proposal-card">
        <div className="proposal-heading">
          <span className="agent-avatar">
            <Sparkles size={14} />
          </span>
          <strong>Proposed task</strong>
          <span className="chip chip-agent">Proposed</span>
          <span className="chip chip-success">Low risk</span>
        </div>
        <div className="proposal-body">
          <h3>Login returns 500 for SSO accounts</h3>
          <div className="proposal-properties">
            <span className="property-pill">
              <span className="text-muted">Priority</span>
              <Flag size={14} className="text-danger" />
              P1 High
            </span>
            <span className="property-pill">
              <span className="text-muted">Owner</span>
              <span className="avatar avatar-small avatar-blue">O</span>Omar
            </span>
          </div>
          <div className="proposal-sources">
            <span>
              <MessageSquare size={13} />
              12 messages
            </span>
            <span>
              <Link2 size={13} />
              BUG-41
            </span>
          </div>
        </div>
        <div className="proposal-footer">
          <span>Nothing is created until you approve</span>
          <span className="preview-button">Edit</span>
          <span className="preview-button preview-primary">Approve</span>
        </div>
      </div>
    </figure>
  );
}

/** Layered radial gradients with slow drifting blobs. Pure CSS (transform only); frozen under prefers-reduced-motion. */
export function AuroraBackground() {
  return (
    <div className="aurora" aria-hidden="true" data-testid="aurora-background">
      <div className="aurora__blob aurora__blob--teal" />
      <div className="aurora__blob aurora__blob--violet" />
      <div className="aurora__blob aurora__blob--blue" />
      <div className="aurora__veil" />
    </div>
  );
}

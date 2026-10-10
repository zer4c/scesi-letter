export function BrandPanel({ compact = false }) {
  return (
    <section className={`brand-panel${compact ? ' brand-panel--compact' : ''}`} aria-label="SCESI Letter">
      <div className="brand-panel__content">
        <div className="brand-lockup" aria-label="SCESI Letter">
          <span className="brand-lockup__name">SCESI</span>
          <span className="brand-lockup__product">Correspondencia académica</span>
        </div>
        <div className="brand-panel__message">
          <h2>Cartas para tu comunidad.</h2>
          <p className="brand-panel__description">
            Redacta, revisa y comparte las cartas de tu comunidad.
          </p>
        </div>
      </div>
      <div className="brand-panel__signature" aria-hidden="true">
        <span />
        <span />
      </div>
      <p className="brand-panel__institution">Sociedad Científica de Estudiantes de Sistemas e Informática</p>
    </section>
  );
}

export function BrandWordmark() {
  return (
    <span className="brand-wordmark" aria-label="SCESI Letter">
      <span className="brand-wordmark__name">SCESI</span>
      <span className="brand-wordmark__divider" aria-hidden="true" />
      <span className="brand-wordmark__product">Letter</span>
    </span>
  );
}

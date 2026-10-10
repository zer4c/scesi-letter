import { useEffect, useState } from 'react';

import { createAutomation, listAutomations, runAutomation } from '../../core/api.js';

function AutomationPage() {
  const [automations, setAutomations] = useState([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [action, setAction] = useState('notify');
  const [message, setMessage] = useState('');

  const load = async () => {
    try {
      setAutomations(await listAutomations());
    } catch {
      setMessage('No se pudo conectar con la API.');
    }
  };

  useEffect(() => { load(); }, []);

  const create = async (event) => {
    event.preventDefault();
    try {
      await createAutomation({ name, description, action });
      setName('');
      setDescription('');
      setMessage('Automatización creada.');
      load();
    } catch {
      setMessage('Completa el nombre de la automatización.');
    }
  };

  const run = async (id) => {
    try {
      const result = await runAutomation(id);
      setMessage(result.message);
    } catch {
      setMessage('No se pudo ejecutar la automatización.');
    }
  };

  return (
    <main className="shell">
      <header>
        <p className="eyebrow">SCESI / AUTOMATIONS</p>
        <h1>Automatiza tu trabajo.</h1>
        <p className="intro">Crea y ejecuta flujos simples desde una interfaz limpia. El estado actual vive en memoria.</p>
      </header>
      <section className="grid">
        <form className="card form" onSubmit={create}>
          <h2>Nueva automatización</h2>
          <label>Nombre <input value={name} onChange={(event) => setName(event.target.value)} required placeholder="Ej. Reporte diario" /></label>
          <label>Descripción <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows="3" placeholder="Qué debe hacer" /></label>
          <label>Acción
            <select value={action} onChange={(event) => setAction(event.target.value)}><option value="notify">Notificar</option><option value="generate_report">Generar reporte</option><option value="webhook">Webhook</option></select>
          </label>
          <button type="submit">Crear automatización</button>
        </form>
        <section className="card list">
          <div className="list-header"><h2>Automatizaciones</h2><button type="button" className="secondary" onClick={load}>Actualizar</button></div>
          {!automations.length && <p className="empty">Todavía no hay automatizaciones.</p>}
          {automations.map((item) => <article key={item.id} className="automation">
            <div><h3>{item.name}</h3><p>{item.description || 'Sin descripción'}</p><small>{item.action}</small></div>
            <button type="button" onClick={() => run(item.id)}>Ejecutar</button>
          </article>)}
        </section>
      </section>
      {message && <p className="message">{message}</p>}
    </main>
  );
}

export default AutomationPage;

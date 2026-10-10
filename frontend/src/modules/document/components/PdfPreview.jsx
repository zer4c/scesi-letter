import * as pdfjs from 'pdfjs-dist';
import { useCallback, useEffect, useRef, useState } from 'react';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

function PdfPage({ document, pageNumber, width, onRenderError }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    let active = true;
    let renderTask;
    document.getPage(pageNumber).then((page) => {
      if (!active || !canvasRef.current) return;
      const ratio = window.devicePixelRatio || 1;
      const baseViewport = page.getViewport({ scale: 1 });
      const scale = Math.min(width / baseViewport.width, 1.6);
      const viewport = page.getViewport({ scale: scale * ratio });
      const canvas = canvasRef.current;
      const context = canvas.getContext('2d', { alpha: false });
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      canvas.style.width = `${Math.ceil(viewport.width / ratio)}px`;
      canvas.style.height = `${Math.ceil(viewport.height / ratio)}px`;
      renderTask = page.render({ canvas, canvasContext: context, viewport });
      return renderTask.promise;
    }).catch((error) => {
      if (active && error?.name !== 'RenderingCancelledException') onRenderError();
    });
    return () => {
      active = false;
      renderTask?.cancel();
    };
  }, [document, pageNumber, width, onRenderError]);

  return <canvas aria-label={`Página ${pageNumber}`} className="pdf-page__canvas" ref={canvasRef} role="img" />;
}

export default function PdfPreview({ source }) {
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [document, setDocument] = useState(null);
  const [pageCount, setPageCount] = useState(0);
  const [error, setError] = useState(false);
  const handleRenderError = useCallback(() => setError('RenderError'), []);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setContainerWidth(Math.max(0, Math.floor(entry.contentRect.width - 32)));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!source) return undefined;
    let active = true;
    const task = pdfjs.getDocument({ url: source });
    setDocument(null);
    setPageCount(0);
    setError(false);
    task.promise.then((pdf) => {
      if (!active) {
        pdf.destroy();
        return;
      }
      setDocument(pdf);
      setPageCount(pdf.numPages);
    }).catch((loadError) => {
      if (active) setError(loadError?.name || 'UnknownError');
    });
    return () => {
      active = false;
      task.destroy();
    };
  }, [source]);

  return (
    <div aria-label="Páginas del PDF" className="pdf-preview" ref={containerRef}>
      {error && <p className="pdf-preview__message" data-error-code={error} role="status">No se pudo representar el PDF en esta ventana. Puedes descargar la vista previa.</p>}
      {!error && !document && <p className="pdf-preview__message" role="status">Cargando páginas del PDF…</p>}
      {document && containerWidth > 0 && Array.from({ length: pageCount }, (_, index) => (
        <div className="pdf-page" key={`${source}-${index + 1}`}>
          <PdfPage document={document} pageNumber={index + 1} width={containerWidth} onRenderError={handleRenderError} />
        </div>
      ))}
    </div>
  );
}

/** Export the currently rendered viewport as a PNG. */
export async function exportViewportSnapshot(fileStem: string): Promise<void> {
  const canvas = document.querySelector<HTMLCanvasElement>(".viewport-3d canvas");
  if (canvas) {
    const blob = await canvasToBlob(canvas);
    download(blob, `${sanitize(fileStem)}-scene.png`);
    return;
  }

  const svg = document.querySelector<SVGSVGElement>(".viewport-2d .viewport-svg");
  if (!svg) throw new Error("No viewport is currently available to export.");
  const serialized = new XMLSerializer().serializeToString(svg);
  const source = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(source);
  try {
    const image = await loadImage(url);
    const output = document.createElement("canvas");
    output.width = 1800;
    output.height = 1120;
    const context = output.getContext("2d");
    if (!context) throw new Error("PNG export is unavailable in this browser.");
    context.fillStyle = "#0e1013";
    context.fillRect(0, 0, output.width, output.height);
    context.drawImage(image, 0, 0, output.width, output.height);
    download(await canvasToBlob(output), `${sanitize(fileStem)}-map.png`);
  } finally {
    URL.revokeObjectURL(url);
  }
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Could not capture the viewport."))),
      "image/png",
      1,
    ),
  );
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Could not render the 2D map for export."));
    image.src = url;
  });
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function sanitize(name: string): string {
  return name.replace(/[^a-z0-9._-]+/gi, "_").slice(0, 80) || "study";
}


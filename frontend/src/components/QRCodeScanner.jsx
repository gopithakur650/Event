import React, { useEffect, useRef, useState } from "react";
import QrScanner from "qr-scanner";

export default function QRCodeScanner({ onScan }) {
  const videoRef = useRef(null);
  const [cameraError, setCameraError] = useState("");

  useEffect(() => {
    if (!videoRef.current) return undefined;
    const scanner = new QrScanner(
      videoRef.current,
      (result) => onScan(result.data),
      { highlightScanRegion: true, highlightCodeOutline: true },
    );
    scanner.start().catch((error) => {
      setCameraError(error.message || "Camera access is not available.");
    });
    return () => scanner.destroy();
  }, [onScan]);

  return <div className="scanner-panel">
    <video ref={videoRef} className="scanner-video" muted playsInline />
    {cameraError && <p className="notice error">{cameraError} You can enter the ticket token below instead.</p>}
  </div>;
}

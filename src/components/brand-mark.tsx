"use client";

// RESOLVEIQ Official Brand Mark: Featuring the RIQ monogram logo
export function BrandMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  const radius = Math.max(6, Math.round(size * 0.22));
  return (
    <span
      className={`brand-mark-frame ${className}`.trim()}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        minWidth: size,
        minHeight: size,
        borderRadius: `${radius}px`,
        overflow: "hidden",
        backgroundColor: "#ffffff",
        boxShadow: "0 1px 3px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0, 0, 0, 0.08)",
        flexShrink: 0,
        position: "relative",
      }}
    >
      <img
        src="/logo.jpeg"
        alt="ResolveIQ Logo"
        width={size}
        height={size}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          display: "block",
        }}
      />
    </span>
  );
}


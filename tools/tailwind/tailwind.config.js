// Cấu hình chuyển nguyên từ khối tailwind.config trong backend/static/index.html (bản CDN 3.4.17).
// Thêm class mới trong index.html / app.js thì chạy lại: npm run build (trong thư mục này).
module.exports = {
  content: ["../../backend/static/index.html", "../../backend/static/app.js"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
        },
      },
      keyframes: {
        kenburnsZoomIn: { "0%": { transform: "scale(1.0)" }, "100%": { transform: "scale(1.2)" } },
        kenburnsZoomOut: { "0%": { transform: "scale(1.2)" }, "100%": { transform: "scale(1.0)" } },
        kenburnsPanLeft: { "0%": { transform: "scale(1.15) translateX(4%)" }, "100%": { transform: "scale(1.15) translateX(-4%)" } },
        kenburnsPanRight: { "0%": { transform: "scale(1.15) translateX(-4%)" }, "100%": { transform: "scale(1.15) translateX(4%)" } },
      },
      animation: {
        "kb-zoom-in": "kenburnsZoomIn 6s ease-in-out infinite alternate",
        "kb-zoom-out": "kenburnsZoomOut 6s ease-in-out infinite alternate",
        "kb-pan-left": "kenburnsPanLeft 6s ease-in-out infinite alternate",
        "kb-pan-right": "kenburnsPanRight 6s ease-in-out infinite alternate",
      },
    },
  },
};

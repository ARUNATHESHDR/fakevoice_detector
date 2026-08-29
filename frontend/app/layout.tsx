import "./globals.css";

export const metadata = {
  title: "Voice Integrity Console",
  description: "Real-time voice cloning / impersonation risk detection",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

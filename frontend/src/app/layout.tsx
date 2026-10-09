import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'CATMS | Clinic workspace', description: 'Clinic appointment and treatment management' };
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
 return <html lang="en"><body>{children}</body></html>;
}

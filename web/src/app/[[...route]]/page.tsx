'use client';
import dynamic from 'next/dynamic';

// The screens use window, localStorage and canvas charts throughout: client only.
const Shell = dynamic(() => import('@/screens/Shell'), { ssr: false });

export default function Page() {
  return <Shell />;
}

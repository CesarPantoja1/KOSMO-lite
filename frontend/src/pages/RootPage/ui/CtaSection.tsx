import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/shared/model';

interface CtaSectionProps {
	onComenzar: () => void;
}

export function CtaSection({ onComenzar }: CtaSectionProps) {
	const router = useRouter();
	const user = useAuthStore((s) => s.user);
	return (
		<section className='relative overflow-hidden border-t border-neutral-200 bg-linear-to-r from-primary-500 to-primary-600 py-20'>
			<div className='absolute inset-0 bg-[radial-linear(circle_at_50%_100%,rgba(255,255,255,0.15),transparent_40%)] pointer-events-none' />

			<div className='relative mx-auto max-w-4xl px-6 text-center'>
				<h2 className='text-3xl font-bold text-neutral-0 md:text-4xl'>
					¿Listo para construir?
				</h2>

				<p className='mx-auto mt-5 max-w-2xl text-sm leading-6 text-primary-100'>
					Convierte tu idea en una aplicación real con la guía de la IA y la disciplina de
					Spec Driven Development.
				</p>

				<button
					type='button'
					onClick={user ? () => router.push('/proyecto') : onComenzar}
					className='mt-8 rounded-xl bg-neutral-0 px-7 py-3.5 font-semibold text-primary-600 shadow-xl transition hover:-translate-y-0.5 cursor-pointer'
				>
					{user ? 'Mis Proyectos →' : 'Comenzar ahora →'}
				</button>

				<p className='mt-5 text-xs text-primary-100'>
					Necesitas un API Key para comenzar.
				</p>
			</div>
		</section>
	);
}

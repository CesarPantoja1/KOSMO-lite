import { Ai } from '@/shared/ui';

const steps = [
	['01', 'Idea', 'Tu conocimiento'],
	['02', 'Descubrimiento', 'IA'],
	['03', 'Funcionalidades', 'IA + negocio'],
	['04', 'Criterios', 'Especificación'],
	['05', 'Diagramas', 'Modelo'],
	['06', 'Implementación', 'Generación'],
	['07', 'Aplicación', 'Resultado'],
];

const sddItems = [
	'Primero entendemos el negocio.',
	'Después definimos qué debe hacer el sistema.',
	'Convertimos las funcionalidades en especificaciones.',
	'Modelamos el comportamiento esperado.',
	'Finalmente generamos el código.',
];

export function SddSection() {
	return (
		<section id='metodologia' className='border-t border-neutral-200 py-24'>
			<div className='mx-auto grid max-w-7xl items-center gap-14 px-6 lg:grid-cols-2'>
				<div>
					<p className='text-xs font-medium uppercase tracking-[0.25em] text-neutral-400'>
						La metodología
					</p>

					<h2 className='mt-4 text-4xl font-bold text-neutral-800'>
						Spec Driven
						<span className='text-neutral-800'> Development</span>
					</h2>

					<p className='mt-6 leading-8 text-neutral-500'>
						KOSMO utiliza Spec Driven Development para que el software no empiece
						directamente con código. Primero se entiende el problema, se define el
						comportamiento esperado y después se construye.
					</p>

					<div className='mt-8 space-y-4'>
						{sddItems.map((item, index) => (
							<div key={item} className='flex items-center gap-4'>
								<div className='flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-neutral-100 text-xs text-neutral-500'>
									{index + 1}
								</div>

								<span className='text-sm text-neutral-700'>{item}</span>
							</div>
						))}
					</div>
				</div>

				<div className='rounded-3xl border border-neutral-200 bg-neutral-50 p-8'>
					<div className='mb-8 flex items-center justify-between'>
						<div>
							<p className='text-xs text-neutral-500'>KOSMO Method</p>
							<h3 className='mt-1 text-lg font-semibold text-neutral-800'>
								Idea → Specification → Software
							</h3>
						</div>

						<div className='flex h-12 w-12 items-center justify-center rounded-xl border bg-neutral-100 border-neutral-200'>
							<Ai size={20} color='text-neutral-500' />
						</div>
					</div>

					<div className='space-y-3'>
						{steps.map(([number, title, description], index) => (
							<div key={number}>
								<div className='flex items-center gap-4 rounded-xl border border-neutral-200 bg-neutral-0 p-4'>
									<span className='text-xs font-medium text-neutral-400'>{number}</span>

									<div className='flex-1'>
										<p className='text-sm font-medium text-neutral-800'>{title}</p>
										<p className='mt-1 text-xs text-neutral-500'>{description}</p>
									</div>

									{index < 6 && <span className='text-neutral-300'>↓</span>}
								</div>
							</div>
						))}
					</div>
				</div>
			</div>
		</section>
	);
}

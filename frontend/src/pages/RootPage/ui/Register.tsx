'use client';

import { authApi } from '@/entities/user';
import { formatApiError } from '@/shared/api';
import { Close } from '@/shared/ui';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

interface RegisterModalProps {
	onClose: () => void;
	onSwitchToLogin: () => void;
}

const Register = ({ onClose, onSwitchToLogin }: RegisterModalProps) => {
	const router = useRouter();

	const [name, setName] = useState('');
	const [email, setEmail] = useState('');
	const [password, setPassword] = useState('');
	const [confirmPassword, setConfirmPassword] = useState('');

	const [error, setError] = useState('');
	const [isLoading, setIsLoading] = useState(false);

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!name.trim() || !email.trim() || !password || !confirmPassword) {
			setError('Todos los campos son obligatorios');
			return;
		}

		if (password !== confirmPassword) {
			setError('Las contraseñas no coinciden');
			return;
		}

		if (password.length < 12) {
			setError('La contraseña debe tener al menos 12 caracteres');
			return;
		}

		setIsLoading(true);
		setError('');

		try {
			await authApi.register(name, email, password);
			await authApi.login(email, password);
			router.push('/onboarding');
			onClose();
		} catch (err) {
			const status = (err as { status?: number }).status;
			if (status === 409) {
				setError('Este correo ya está registrado');
			} else if (status === 429) {
				const retryAfter = (err as { retryAfter?: number }).retryAfter;
				setError(
					retryAfter
						? `Demasiadas solicitudes. Intente de nuevo en ${retryAfter} segundos.`
						: 'Demasiadas solicitudes. Intente de nuevo más tarde.',
				);
			} else {
				setError(formatApiError(err, 'Error al registrar usuario'));
			}
		} finally {
			setIsLoading(false);
		}
	};

	return (
		<form
			onSubmit={handleSubmit}
			className='bg-neutral-0 p-8 rounded-xl shadow-lg border border-neutral-200'
		>
			<div className='flex items-center justify-between mb-8'>
				<div className='text-center flex-1'>
					<h1 className='text-3xl font-bold text-primary-500'>KOSMO</h1>
					<p className='text-neutral-500 mt-2'>Crear cuenta</p>
				</div>
				<button
					type='button'
					onClick={onClose}
					className='text-neutral-400 hover:text-neutral-600 transition-colors'
				>
					<Close size={20} color='text-current' />
				</button>
			</div>

			{error && (
				<div className='bg-error-50 border border-error-500/50 text-error-700 p-3 rounded-lg mb-4 text-sm'>
					{error}
				</div>
			)}

			<div className='flex flex-col gap-4'>
				<div>
					<label
						htmlFor='register-name'
						className='block text-neutral-600 text-sm font-medium mb-1.5'
					>
						Nombre completo
					</label>
					<input
						id='register-name'
						type='text'
						className='w-full bg-neutral-50 border border-neutral-300 text-neutral-800 rounded-lg px-3 py-2.5 outline-none focus:border-primary-500 transition-colors placeholder:text-neutral-400'
						placeholder='Tu nombre y apellido'
						value={name}
						onChange={(e) => setName(e.target.value)}
						disabled={isLoading}
						autoComplete='name'
					/>
				</div>
				<div>
					<label
						htmlFor='register-email'
						className='block text-neutral-600 text-sm font-medium mb-1.5'
					>
						Correo electrónico
					</label>
					<input
						id='register-email'
						type='email'
						className='w-full bg-neutral-50 border border-neutral-300 text-neutral-800 rounded-lg px-3 py-2.5 outline-none focus:border-primary-500 transition-colors placeholder:text-neutral-400'
						placeholder='tu@email.com'
						value={email}
						onChange={(e) => setEmail(e.target.value)}
						disabled={isLoading}
						autoComplete='email'
					/>
				</div>
				<div>
					<label
						htmlFor='register-password'
						className='block text-neutral-600 text-sm font-medium mb-1.5'
					>
						Contraseña
					</label>
					<input
						id='register-password'
						type='password'
						className='w-full bg-neutral-50 border border-neutral-300 text-neutral-800 rounded-lg px-3 py-2.5 outline-none focus:border-primary-500 transition-colors placeholder:text-neutral-400'
						placeholder='Mínimo 12 caracteres'
						value={password}
						onChange={(e) => setPassword(e.target.value)}
						disabled={isLoading}
						autoComplete='new-password'
					/>
				</div>
				<div>
					<label className='block text-neutral-600 text-sm font-medium mb-1.5'>
						Confirmar contraseña
					</label>
					<input
						type='password'
						className='w-full bg-neutral-50 border border-neutral-300 text-neutral-800 rounded-lg px-3 py-2.5 outline-none focus:border-primary-500 transition-colors placeholder:text-neutral-400'
						placeholder='Repite tu contraseña'
						value={confirmPassword}
						onChange={(e) => setConfirmPassword(e.target.value)}
						disabled={isLoading}
						autoComplete='new-password'
					/>
				</div>
				<button
					type='submit'
					disabled={isLoading}
					className='btn btn-primary btn-lg w-full mt-2'
				>
					{isLoading ? 'Registrando...' : 'Registrarse'}
				</button>

				<div className='text-center mt-2'>
					<button
						type='button'
						onClick={onSwitchToLogin}
						className='text-primary-500 hover:text-primary-600 text-sm font-medium transition-colors'
					>
						¿Ya tienes cuenta? Inicia sesión
					</button>
				</div>
			</div>
		</form>
	);
};

export { Register };

import { z } from 'zod'
import type { Project } from '@/entities/project'

const hasEmoji = (value: string) => /\p{Extended_Pictographic}/u.test(value)

const baseProjectSchema = z.object({
  name: z
    .string()
    .min(3, 'Mínimo 3 caracteres')
    .max(25, 'Máximo 25 caracteres')
    .regex(/^[a-zA-Z\s]+$/, 'No se permiten caracteres especiales')
    .refine((val) => !hasEmoji(val), 'No se permiten emojis'),
  description: z
    .string()
    .min(50, 'Mínimo 50 caracteres')
    .max(1000, 'Máximo 1000 caracteres')
    .refine((val) => !hasEmoji(val), 'No se permiten emojis'),
  repo_name: z.string(),
  is_public: z.boolean(),
})

export type ProjectFormData = z.infer<typeof baseProjectSchema>

export function createProjectSchema(existingProjects: Project[]) {
  return baseProjectSchema.refine(
    (val) =>
      !existingProjects.some(
        (p) => p.name.toLowerCase().trim() === val.name.toLowerCase().trim(),
      ),
    { message: 'Ya existe un proyecto con ese nombre', path: ['name'] },
  )
}

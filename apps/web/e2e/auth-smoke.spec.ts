import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('http://127.0.0.1:8000/**', async (route) => {
    const path = new URL(route.request().url()).pathname

    if (path === '/health') {
      await route.fulfill({ json: { status: 'ok' } })
      return
    }
    if (path === '/api/v1/product') {
      await route.fulfill({
        json: {
          name: 'ApplyLens AI',
          version: '0.1.0-beta.1',
          release_channel: 'free-public-beta',
          phase: 'Free public beta launch candidate',
          supported_opportunities: ["Master's", 'PhD'],
          promise: 'Every decision is backed by evidence or marked unclear.',
          support_email: null,
        },
      })
      return
    }
    if (path === '/api/v1/auth/me') {
      await route.fulfill({ status: 401, json: { detail: 'Not authenticated' } })
      return
    }

    await route.continue()
  })
})

test('loads the sign-in experience and exposes registration and legal details', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible()

  await page.getByRole('button', { name: 'Need an account? Register' }).click()
  await expect(page.getByRole('heading', { name: 'Create your workspace.' })).toBeVisible()
  await expect(page.getByLabel('Password (at least 12 characters)')).toHaveAttribute(
    'minlength',
    '12',
  )

  await page.getByRole('button', { name: 'Privacy, terms & support' }).click()
  await expect(page.getByRole('heading', { name: 'Privacy, terms & support' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Terms of use' })).toBeVisible()
  await expect(page.getByText(/or guarantee eligibility, admission, funding/i)).toBeVisible()
})

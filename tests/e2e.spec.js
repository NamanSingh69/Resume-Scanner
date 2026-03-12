const { test, expect } = require('@playwright/test');

test.describe('Resume Scanner ATS E2E', () => {
    test.beforeEach(async ({ page }) => {
        // Assume the app is running on localhost:5000 during test execution
        await page.goto('http://127.0.0.1:5000');
    });

    test('Loads the app correctly', async ({ page }) => {
        await expect(page).toHaveTitle(/Resume ATS Scanner/i);
        await expect(page.locator('h1')).toContainText('Resume ATS Scanner');
        
        // Empty state should be visible initially
        await expect(page.locator('#empty-state-container')).toBeVisible();
        await expect(page.locator('#results')).toBeHidden();
        
        // Gemini UI elements should be injected
        await expect(page.locator('#gemini-mode-toggle')).toBeVisible();
    });

    // We can't actually do a full mocked API call easily without intercepting network or having API key
    // But we can check validation logic on the UI
    test('Shows validation error if file is missing', async ({ page }) => {
        await page.fill('#job-desc', 'Looking for a senior developer.');
        // Click analyze without file
        await page.click('#submit-btn');
        
        // Expect a toast notification
        const toast = page.locator('#toast-container div');
        await expect(toast).toBeVisible();
        await expect(toast).toContainText('Please upload a resume');
    });

    // Mock API call test
    test('Simulates a successful scan report', async ({ page }) => {
        // Intercept API call
        await page.route('/api/analyze', async route => {
            const json = {
                "ats_score": 85,
                "component_scores": { "Skills Match": 90, "Experience": 80, "Formatting": 85 },
                "ai_feedback": ["Great match!", "Add some quantitative metrics constraints."],
                "matched_keywords": ["Developer", "React"],
                "missing_keywords": ["Node.js"]
            };
            await route.fulfill({ json });
        });

        // Fill data
        await page.fill('#job-desc', 'Looking for a developer with React.');
        
        // Upload a dummy text file
        const fileInput = page.locator('#resume-file');
        await fileInput.setInputFiles({
            name: 'resume.txt',
            mimeType: 'text/plain',
            buffer: Buffer.from('Here is my resume with React experience.')
        });

        // Click Analyze
        await page.click('#submit-btn');
        
        // Loading state should show
        await expect(page.locator('#loading')).toBeHidden({ timeout: 5000 });
        
        // Results should show
        await expect(page.locator('#results')).toBeVisible();
        
        // Verify score is 85
        await expect(page.locator('#score-text')).toHaveText('85');
        
        // Verify keywords
        await expect(page.locator('#keywords')).toContainText('✓ Developer');
        await expect(page.locator('#keywords')).toContainText('✗ Node.js');
        
        // Toast shows success
        const toast = page.locator('#toast-container div').last();
        await expect(toast).toBeVisible();
        await expect(toast).toContainText('successfully analyzed');
    });
});

<script lang="ts">
	import { getContext } from 'svelte';
	import { settings } from '$lib/stores';
	import Modal from './common/Modal.svelte';
	import { updateUserSettings } from '$lib/apis/users';
	import XMark from '$lib/components/icons/XMark.svelte';

	const i18n = getContext('i18n');

	export let show = false;

	const closeModal = async () => {
		await settings.set({ ...$settings, regosDisclaimerAcked: true });
		await updateUserSettings(localStorage.token, { ui: $settings });
		show = false;
	};
</script>

<Modal bind:show size="md">
	<div class="px-6 pt-5 dark:text-white text-black">
		<div class="flex justify-between items-start">
			<div class="text-xl font-medium">
				RegOS Compliance Copilot
			</div>
			<button class="self-center" on:click={closeModal} aria-label={$i18n.t('Close')}>
				<XMark className={'size-5'}>
					<p class="sr-only">{$i18n.t('Close')}</p>
				</XMark>
			</button>
		</div>
		<div class="flex items-center mt-1">
			<div class="text-sm dark:text-gray-200">Service Agreement</div>
		</div>
	</div>

	<div class="w-full p-4 px-6 text-gray-700 dark:text-gray-100">
		<div class="space-y-4 text-sm leading-relaxed">
			<p>
				RegOS analyses are <strong>AI-assisted regulatory reviews</strong> based on
				Miami-Dade County Chapter 24 environmental regulations. All outputs are
				professional-grade starting points intended for use within a professional
				compliance workflow.
			</p>

			<p>
				Users are expected to apply domain expertise, site-specific context, and
				current regulatory interpretations as part of their standard review process.
			</p>

			<div class="rounded-xl bg-gray-50 dark:bg-gray-850/50 p-4 space-y-2">
				<div class="font-semibold text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
					What each analysis includes
				</div>
				<div class="grid grid-cols-1 gap-2 text-sm">
					<div class="flex items-start gap-2">
						<span class="text-blue-500 mt-0.5">●</span>
						<span><strong>Source Confidence Score</strong> — quantified retrieval quality (0–100%)</span>
					</div>
					<div class="flex items-start gap-2">
						<span class="text-green-500 mt-0.5">●</span>
						<span><strong>Cited Regulatory Sections</strong> — exact Chapter 24 references</span>
					</div>
					<div class="flex items-start gap-2">
						<span class="text-yellow-500 mt-0.5">●</span>
						<span><strong>Threshold Evaluation</strong> — COMPLIANT / BREACH / BORDERLINE determinations</span>
					</div>
					<div class="flex items-start gap-2">
						<span class="text-red-500 mt-0.5">●</span>
						<span><strong>Gaps & Limitations</strong> — transparent about coverage scope</span>
					</div>
				</div>
			</div>

			<p class="text-xs text-gray-400 dark:text-gray-500">
				By continuing, you acknowledge this guidance and agree to use RegOS outputs
				within your professional compliance workflow.
			</p>
		</div>

		<div class="flex justify-end pt-4 text-sm font-medium">
			<button
				on:click={closeModal}
				class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
			>
				<span class="relative">I Understand, Let's Go</span>
			</button>
		</div>
	</div>
</Modal>

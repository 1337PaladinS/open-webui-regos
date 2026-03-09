<script lang="ts">
	import Info from '$lib/components/icons/Info.svelte';
	import { user } from '$lib/stores';

	export let content = '';

	$: isGuestLimit =
		$user?.role === 'guest' &&
		typeof content === 'string' &&
		content.toLowerCase().includes('guest message limit');
</script>

<div class="flex my-2 gap-2.5 border px-4 py-3 border-red-600/10 bg-red-600/10 rounded-lg">
	<div class=" self-start mt-0.5">
		<Info className="size-5 text-red-700 dark:text-red-400" />
	</div>

	<div class=" self-center text-sm">
		{#if isGuestLimit}
			<span>You've used all your free guest messages.</span>
			<a
				href="/auth?form=signup"
				class="ml-1 font-semibold underline text-red-700 dark:text-red-300 hover:text-red-900 dark:hover:text-red-100"
			>
				Sign up for unlimited access &rarr;
			</a>
		{:else if typeof content === 'string'}
			{content}
		{:else if typeof content === 'object' && content !== null}
			{#if content?.error && content?.error?.message}
				{content.error.message}
			{:else if content?.detail}
				{content.detail}
			{:else if content?.message}
				{content.message}
			{:else}
				{JSON.stringify(content)}
			{/if}
		{:else}
			{JSON.stringify(content)}
		{/if}
	</div>
</div>

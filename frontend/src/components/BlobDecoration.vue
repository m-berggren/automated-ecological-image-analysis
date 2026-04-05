<!-- Author: Claudia Sevilla -->
<!-- Blob decoration ported from Lovable's React prototype -->

<template>
  <div class="pointer-events-none inset-0 overflow-hidden -z-10">
    <!-- Large sage blob top-right -->
    <div class="absolute -top-32 -right-32 w-[500px] h-[500px] rounded-full bg-blob-1 opacity-40 blur-3xl animate-blob-float" />
    <!-- Mint blob bottom-left -->
    <div class="absolute -bottom-40 -left-40 w-[600px] h-[600px] rounded-full bg-blob-2 opacity-30 blur-3xl animate-blob-float-reverse" />
    <!-- Small accent blob mid -->
    <div
      class="absolute top-1/2 left-1/3 w-[300px] h-[300px] rounded-full bg-blob-3 opacity-25 blur-3xl animate-blob-float"
      style="animation-delay: 4s"
    />
    <!-- Greyish-blue blob top-left -->
    <div
      class="absolute -top-20 -left-24 w-[450px] h-[450px] rounded-full bg-blob-4 opacity-30 blur-3xl animate-blob-float-reverse"
      style="animation-delay: 2s"
    />
    <!-- Greyish-blue blob bottom-right -->
    <div
      class="absolute bottom-[10%] right-[5%] w-[350px] h-[350px] rounded-full bg-blob-5 opacity-25 blur-3xl animate-blob-float"
      style="animation-delay: 6s"
    />

    <div class="absolute top-20 left-[15%] w-3 h-3 rounded-full bg-bbox-pink opacity-60 animate-bbox-pulse" />
    <div
      class="absolute top-[60%] right-[20%] w-2 h-2 rounded-full bg-bbox-cyan opacity-50 animate-bbox-pulse"
      style="animation-delay: 1s"
    />
    <div
      class="absolute bottom-[30%] left-[60%] w-2.5 h-2.5 rounded-full bg-bbox-lime opacity-50 animate-bbox-pulse"
      style="animation-delay: 0.5s"
    />
  </div>
</template>
/* Recipe media only: never substitute a creator's avatar or an arbitrary resource. */
(() => {
 'use strict';
 const safeURL=value=>typeof value==='string'&&(
   value.startsWith('https://')||/^data:image\/(?:jpeg|png|webp);base64,/.test(value))?value:'';
 function photoURL(recipe) {
   if(recipe.photo)return safeURL(recipe.photo);
   const resources=Array.isArray(recipe.resourceMedias)?recipe.resourceMedias:[];
   const covers=[recipe.cover,...resources.filter(item=>item?.isCover===true)];
   for(const cover of covers){
     const media=cover?.media;
     if(!media||media.isDisabled===true||media.type!=='PHOTO')continue;
     const url=safeURL(media.original)||safeURL(media.thumbnail);
     if(url)return url;
   }
   return '';
 }
 window.recipeMedia={photoURL};
})();

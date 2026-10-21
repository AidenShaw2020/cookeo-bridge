/* The list uses recipe-wide community data; mobile detail also has per-variant data. */
(() => {
 'use strict';
 const text=value=>typeof value==='string'?value:'';
 function authorName(recipe){
   const creator=recipe.creator;
   return text(typeof creator==='string'?creator:creator?.nickname||creator?.name)||text(recipe.author)||tr('Autor neuveden');
 }
 function community(recipe){
   const top=recipe.communityTopRecipe;
   return top&&Object.hasOwn(top,'rating')?top:(recipe.community||{});
 }
 function ratingText(recipe){
   const value=community(recipe),rating=Number(value.rating),count=Number(value.raters);
   return Number.isFinite(rating)&&rating>0?'★ '+rating.toFixed(1)+(count?' ('+count+')':''):tr('Bez hodnocení');
 }
 function scaledQuantity(value,factor){
   const source=String(value??'').trim().replace(',','.');
   const fraction=source.match(/^(\d+)\/(\d+)$/);
   const number=fraction&&Number(fraction[2])?Number(fraction[1])/Number(fraction[2]):/^\d+(?:\.\d+)?$/.test(source)?Number(source):NaN;
   return Number.isFinite(number)?Number((number*factor).toFixed(2)).toLocaleString(window.uiLanguage):String(value??'');
 }
 function ingredientLabel(ingredient,factor=1){
   if(typeof ingredient==='string')return ingredient;
   const description=ingredient.applicationDescription||ingredient.applianceDescription||ingredient.name||ingredient.food?.name||'';
   const quantity=ingredient.quantity;
   if(quantity===undefined||quantity===null)return description;
   const prefix=description.match(/^\s*(\d+(?:[.,]\d+)?(?:\/\d+)?)\s*/);
   if(prefix){
     const raw=prefix[1].replace(',','.').split('/'),number=Number(raw[0])/(raw.length>1?Number(raw[1]):1);
     if(Number.isFinite(number)&&Math.abs(number-Number(quantity))<.001)
       return scaledQuantity(quantity,factor)+' '+description.slice(prefix[0].length);
   }
   const unit=ingredient.unit?.abbreviation||ingredient.unit?.name||'';
   return [scaledQuantity(quantity,factor),unit,description].filter(Boolean).join(' ');
 }
 function duration(value){
   const seconds=Number(value);if(!Number.isFinite(seconds)||seconds<=0)return '';
   const minutes=Math.floor(seconds/60),rest=Math.round(seconds%60);
   return [minutes?minutes+' min':'',rest?rest+' s':''].filter(Boolean).join(' ');
 }
 function programKind(key){
   if(['PROGRAM_201857','PROGRAM_201858'].includes(key))return 'pressure';
   if(['PROGRAM_201863','PROGRAM_201862','PROGRAM_201867'].includes(key))return 'sear';
   if(['PROGRAM_201859','PROGRAM_201861'].includes(key))return 'steam';
   if(['PROGRAM_201872','PROGRAM_201875','PROGRAM_201876','PROGRAM_201877','PROGRAM_201878'].includes(key))return 'oven';
   return 'cooker';
 }
 function stepModels(recipe,group='APPLIANCE_GROUP_3019'){
   const ingredients=new Map((recipe.ingredients||[]).map(i=>[i.fid?.functionalId,i]));
   return (recipe.steps||[]).map(step=>({
     text:step.applicationDescription||step.applianceDescription||'',
     ingredients:[...(step.ingredients||[]).map(i=>i.applicationDescription?i:(ingredients.get(i.fid?.functionalId)||i)),...(step.ingredientsWithoutIdentifier||[])],
     operations:(step.sequences||[]).filter(sequence=>sequence.applianceGroup?.key===group).flatMap(sequence=>sequence.operations||[]).map(operation=>{
       const parameters=operation.parameters||[],value=key=>parameters.find(p=>p.commonKey===key)?.value;
       const numeric=key=>{const raw=value(key);return raw!==undefined&&raw!==null&&raw!==''&&Number.isFinite(Number(raw))?Number(raw):undefined;};
       return {name:operation.program?.name||tr('Program hrnce'),kind:programKind(operation.program?.key),
         duration:duration(value('DURATION')),temperature:numeric('TEMPERATURE'),speed:numeric('SPEED')};
     }),
     kind:step.type?.key==='COOKING'?'cooker':'prep'
   }));
 }
 const paths={
   prep:['M5 25h22M7 20l10-10 5 5-10 10M18 9l4-4 5 5-4 4'],
   pressure:['M7 12h18v12a3 3 0 0 1-3 3H10a3 3 0 0 1-3-3ZM5 12h22M12 8h8M16 8V5M4 16h3m18 0h3M12 19h8'],
   steam:['M7 18h18v7H7ZM5 18h22M10 13c-4-4 4-5 0-9m6 9c-4-4 4-5 0-9m6 9c-4-4 4-5 0-9'],
   sear:['M4 13h20l-2 7H7ZM24 15h5M10 25l1 3m6-3-1 3M10 9l2-4m5 4 2-4'],
   oven:['M5 6h22v22H5ZM5 12h22M9 9h1m4 0h1M10 17h12v7H10Z'],
   cooker:['M8 10h16l2 6v8a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4v-8ZM7 10h18M12 6h8M11 16h10v6H11Z']
 };
 function icon(kind){
   const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
   for(const [key,value] of Object.entries({viewBox:'0 0 32 32',fill:'none',stroke:'currentColor','stroke-width':'1.8','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);
   for(const d of paths[kind]||paths.cooker){const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',d);svg.append(path);}
   return svg;
 }
 const node=(tag,value,cls)=>{const n=document.createElement(tag);if(value!==undefined)n.textContent=value;if(cls)n.className=cls;return n;};
 function renderSteps(container,recipe,factor=1){
   container.replaceChildren();
   for(const [index,step] of stepModels(recipe).entries()){
     const item=node('li',undefined,'recipe-step'),head=node('div',undefined,'recipe-step-heading'),number=node('span',String(index+1),'recipe-step-number');
     head.append(number,node('p',step.text));item.append(head);
     const programs=node('div',undefined,'program-bubbles');
     for(const operation of step.operations){
       const bubble=node('div',undefined,'program-bubble');bubble.append(icon(operation.kind));
       const label=node('div');label.append(node('strong',operation.name));
       const parameters=[operation.duration,operation.temperature!==undefined?operation.temperature+' °C':'',operation.speed!==undefined?tr('Míchání')+': '+(Number(operation.speed)===0?tr('Vypnuto'):operation.speed):''].filter(Boolean);
       if(parameters.length)label.append(node('small',parameters.join(' · ')));bubble.append(label);programs.append(bubble);
     }
     if(!step.operations.length){const bubble=node('div',undefined,'program-bubble manual');bubble.append(icon(step.kind),node('span',tr(step.kind==='prep'?'Příprava':'Ruční krok')));programs.append(bubble);}
     item.append(programs);
     if(step.ingredients.length){
       const list=node('ul',undefined,'step-ingredients');list.setAttribute('aria-label',tr('Suroviny v kroku'));
       for(const ingredient of step.ingredients)list.append(node('li',ingredientLabel(ingredient,factor)));
       item.append(list);
     }
     container.append(item);
   }
   if(!container.children.length)container.append(node('li',tr('Textový postup není ve vráceném detailu.')));
 }
 function renderReviews(container,comments){
   container.replaceChildren();
   for(const comment of comments){
     if(comment.status&&comment.status!=='PUBLISHED')continue;
     const article=node('article',undefined,'recipe-review'),head=node('header');
     head.append(node('strong',authorName(comment)));
     const rating=Number(comment.evaluation?.rating);
     if(Number.isFinite(rating)&&rating>0)head.append(node('span','★ '+rating.toFixed(1),'review-rating'));
     const date=new Date(comment.creationDate);
     if(Number.isFinite(date.getTime())){const time=node('time',date.toLocaleDateString(window.uiLanguage));time.dateTime=date.toISOString();head.append(time);}
     article.append(head,node('p',comment.content||''));container.append(article);
   }
 }
 window.recipeDetail={authorName,ratingText,community,ingredientLabel,stepModels,renderSteps,renderReviews};
})();

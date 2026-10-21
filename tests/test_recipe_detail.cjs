const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={window:{uiLanguage:'en'},tr:value=>value};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../cookeo/app/web/recipe-detail.js'),'utf8'),context);
const detail=context.window.recipeDetail;
assert.equal(detail.authorName({creator:'Chef'}),'Chef');
assert.equal(detail.authorName({creator:{nickname:'Chef'}}),'Chef','Mobile creator uses nickname, not name');
assert.equal(detail.authorName({creator:{}}),'Autor neuveden');
assert.equal(detail.ratingText({community:{rating:4,raters:1},communityTopRecipe:{rating:4.7,raters:6}}),'★ 4.7 (6)','Use the aggregate shown on the catalog card');
assert.equal(detail.ratingText({community:{rating:4.7,raters:6}}),'★ 4.7 (6)');
assert.equal(detail.ingredientLabel({quantity:.5,applicationDescription:'0,5 lžičky soli'},2),'1 lžičky soli');
assert.equal(detail.ingredientLabel({quantity:300,applicationDescription:'300 g rýže, namočené'},.5),'150 g rýže, namočené');
const recipe={ingredients:[{fid:{functionalId:'i1'},quantity:200,applicationDescription:'200 ml vody'}],steps:[
 {applicationDescription:'Cook',ingredients:[{fid:{functionalId:'i1'}}],sequences:[
  {applianceGroup:{key:'OTHER'},operations:[{program:{name:'Wrong'},parameters:[]}]},
  {applianceGroup:{key:'APPLIANCE_GROUP_3019'},operations:[{program:{key:'PROGRAM_201858',name:'High pressure'},parameters:[{commonKey:'DURATION',value:'900'},{commonKey:'TEMPERATURE',value:'100'}]}]}]},
 {applicationDescription:'Serve',ingredientsWithoutIdentifier:['Salt to taste']}]};
const steps=detail.stepModels(recipe);
assert.equal(steps.length,2);assert.equal(steps[0].operations.length,1);
assert.equal(steps[0].operations[0].name,'High pressure');assert.equal(steps[0].operations[0].kind,'pressure');
assert.equal(steps[0].operations[0].duration,'15 min');
assert.equal(detail.ingredientLabel(steps[0].ingredients[0],2),'400 ml vody');
assert.equal(steps[1].ingredients[0],'Salt to taste');
console.log('Recipe detail: author, aggregate ratings, step programs, ingredient references and scaling passed.');
